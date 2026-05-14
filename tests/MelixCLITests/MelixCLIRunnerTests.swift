import Foundation
import Testing

@testable import MelixCLICore
import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Melix CLI Runner")
struct MelixCLIRunnerTests {
    @Test("server snapshot renders runtime session metadata")
    func serverSnapshotRendersRuntimeSessionMetadata() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(runtimeSessions: [makeRuntimeSession()]))

        let output = try await MelixCLIRunner(client: client).run(.serverSnapshot(.init()))

        #expect(output.contains("server_state\tserver_session_id\tlifecycle_state"))
        #expect(output.contains("server_ready\tserver-session-1\tready\tactive\tinitial_boot"))
    }

    @Test("model hub search renders typed search results")
    func modelHubSearchRendersTypedSearchResults() async throws {
        let client = StubControlPlaneXPCClient()
        var result = Melix_Controlplane_V1_HubSearchResult()
        result.nextCursor = "cursor:page-2"
        var model = Melix_Controlplane_V1_HubModelSummary()
        model.repoID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        model.pipelineTag = "text-generation"
        model.mlxCompatible = true
        model.localFitStatus = "good"
        model.estimatedResidentBytes = 5_670_000_000
        result.models = [model]
        await client.setHubSearchResult(result)

        let output = try await MelixCLIRunner(client: client).run(
            .modelHubSearch(.init(query: "qwen3.5", pageSize: 5, cursor: "", mlxOnly: true, json: false))
        )

        #expect(output.contains("repo_id\tpipeline_tag\tcompatibility\tlocal_fit_status\testimated_resident_bytes"))
        #expect(output.contains("mlx-community/Qwen3.5-0.8B-OptiQ-4bit\ttext-generation\tmlx"))
        #expect(output.contains("good\t5.28 GB"))
    }

    @Test("model hub show renders typed model cards")
    func modelHubShowRendersTypedModelCards() async throws {
        let client = StubControlPlaneXPCClient()
        var card = Melix_Controlplane_V1_HubModelCard()
        card.repoID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        card.author = "mlx-community"
        card.modelName = "Qwen3.5-0.8B-OptiQ-4bit"
        card.pipelineTag = "text-generation"
        card.mlxCompatible = true
        card.estimatedResidentBytes = 5_670_000_000
        await client.setHubModelCard(card)

        let output = try await MelixCLIRunner(client: client).run(
            .modelHubShow(.init(repoID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit", json: false))
        )

        #expect(output.contains("repo_id=mlx-community/Qwen3.5-0.8B-OptiQ-4bit"))
        #expect(output.contains("author=mlx-community"))
        #expect(output.contains("mlx_compatible=true"))
        #expect(output.contains("estimated_resident_bytes=5.28 GB"))
    }

    @Test("estimate import renders a structured Apple Silicon memory fit receipt")
    func estimateImportRendersStructuredMemoryFitReceipt() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setHubModelCard(
            makeHubModelCard(
                repoID: "mlx-community/Qwen3.6-35B-A3B-4bit",
                localFitStatus: "heavy",
                localFitReasons: [
                    "Estimated resident memory exceeds the comfort budget.",
                    "Quantization metadata was inferred from filename.",
                ],
                estimatedArtifactBytes: 22_000_000_000,
                estimatedResidentBytes: 44_000_000_000,
                recommendedAction: "Use --allow-memory-risk only when the Mac is otherwise idle."
            )
        )

        let output = try await MelixCLIRunner(client: client).run(
            .estimateImport(.init(repoID: "mlx-community/Qwen3.6-35B-A3B-4bit", json: true))
        )
        let payload = try #require(parseJSONObject(output))
        let probe = try #require(payload["probe"] as? [String: Any])
        let safetyThreshold = try #require(payload["safety_threshold"] as? [String: Any])

        #expect(await client.lastHubModelCardRepoID == "mlx-community/Qwen3.6-35B-A3B-4bit")
        #expect(payload["schema_version"] as? String == "melix.memory_fit_receipt.v1")
        #expect(payload["target_kind"] as? String == "import")
        #expect(payload["repo_id"] as? String == "mlx-community/Qwen3.6-35B-A3B-4bit")
        #expect(payload["fit_status"] as? String == "heavy")
        #expect((payload["total_unified_memory_bytes"] as? NSNumber)?.uint64Value ?? 0 > 0)
        #expect((payload["estimated_active_memory_bytes"] as? NSNumber)?.uint64Value == 44_000_000_000)
        #expect((payload["estimated_disk_usage_bytes"] as? NSNumber)?.uint64Value == 22_000_000_000)
        #expect((payload["available_disk_bytes"] as? NSNumber)?.uint64Value ?? 0 > 0)
        #expect(["good", "blocked", "unknown"].contains(payload["disk_fit_status"] as? String ?? ""))
        #expect(payload["recommended_action"] as? String == "Use --allow-memory-risk only when the Mac is otherwise idle.")
        #expect((payload["assumptions"] as? [String])?.isEmpty == false)
        #expect((payload["unknown_fields"] as? [String])?.contains("parameter_count") == true)
        #expect(probe["name"] as? String == "cli.memory_fit.import")
        #expect((probe["hub_card_elapsed_ms"] as? NSNumber)?.doubleValue ?? -1 >= 0)
        #expect((probe["receipt_elapsed_ms"] as? NSNumber)?.doubleValue ?? -1 >= 0)
        #expect((safetyThreshold["safety_threshold_fraction"] as? NSNumber)?.doubleValue == 0.60)
        #expect((safetyThreshold["safety_threshold_bytes"] as? NSNumber)?.uint64Value ?? 0 > 0)
        #expect(safetyThreshold["memory_headroom_fraction"] == nil)
    }

    @Test("estimate import renders a readable memory fit receipt")
    func estimateImportRendersReadableMemoryFitReceipt() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setHubModelCard(
            makeHubModelCard(
                repoID: "mlx-community/Qwen3.5-9B-MLX-4bit",
                localFitStatus: "good",
                localFitReasons: ["Estimated resident memory fits the comfort budget."],
                estimatedArtifactBytes: 5_000_000_000,
                estimatedResidentBytes: 9_000_000_000,
                recommendedAction: "Run import normally."
            )
        )

        let output = try await MelixCLIRunner(client: client).run(
            .estimateImport(.init(repoID: "mlx-community/Qwen3.5-9B-MLX-4bit"))
        )

        #expect(output.contains("target_kind=import"))
        #expect(output.contains("repo_id=mlx-community/Qwen3.5-9B-MLX-4bit"))
        #expect(output.contains("fit_status=good"))
        #expect(output.contains("total_unified_memory_bytes="))
        #expect(output.contains("total_unified_memory_bytes=\(ProcessInfo.processInfo.physicalMemory)") == false)
        #expect(output.contains("estimated_active_memory_bytes=8.38 GB"))
        #expect(output.contains("estimated_disk_usage_bytes=4.66 GB"))
        #expect(output.contains("available_disk_bytes="))
        #expect(output.contains("disk_fit_status="))
        #expect(output.contains("recommended_action=Run import normally."))
    }

    @Test("estimate benchmark eval and train include target-specific unknowns")
    func estimateRunTargetsIncludeTaskSpecificUnknowns() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setHubModelCard(
            makeHubModelCard(
                repoID: "mlx-community/Qwen3.5-9B-MLX-4bit",
                localFitStatus: "good",
                localFitReasons: ["Estimated resident memory fits the comfort budget."],
                estimatedArtifactBytes: 5_000_000_000,
                estimatedResidentBytes: 9_000_000_000,
                recommendedAction: "Run normally."
            )
        )

        for (targetKind, expectedUnknown) in [
            ("benchmark", "kv_cache_bytes"),
            ("eval", "judge_memory_bytes"),
            ("train", "optimizer_state_bytes"),
        ] {
            let output = try await MelixCLIRunner(client: client).run(
                .estimateImport(.init(
                    repoID: "mlx-community/Qwen3.5-9B-MLX-4bit",
                    targetKind: targetKind,
                    targetInputs: ["dataset": "top200"],
                    json: true
                ))
            )
            let payload = try #require(parseJSONObject(output))
            let unknownFields = try #require(payload["unknown_fields"] as? [String])
            let assumptions = try #require(payload["assumptions"] as? [String])
            let targetInputs = try #require(payload["target_inputs"] as? [String: Any])

            #expect(payload["target_kind"] as? String == targetKind)
            #expect((payload["probe"] as? [String: Any])?["name"] as? String == "cli.memory_fit.\(targetKind)")
            #expect(targetInputs["dataset"] as? String == "top200")
            #expect(unknownFields.contains(expectedUnknown))
            #expect(assumptions.contains { $0.contains("not separately modeled yet") })
        }
    }

    @Test("estimate import reports unknown fields when Hub fit evidence is sparse")
    func estimateImportReportsSparseHubUnknownFields() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setHubModelCard(
            makeHubModelCard(
                repoID: "mlx-community/metadata-light-model",
                localFitStatus: "",
                localFitReasons: [],
                estimatedArtifactBytes: 0,
                estimatedResidentBytes: 0,
                recommendedAction: ""
            )
        )

        let output = try await MelixCLIRunner(client: client).run(
            .estimateImport(.init(repoID: "mlx-community/metadata-light-model", json: true))
        )
        let payload = try #require(parseJSONObject(output))
        let unknownFields = try #require(payload["unknown_fields"] as? [String])

        #expect(payload["fit_status"] as? String == "unknown")
        #expect(unknownFields.contains("estimated_active_memory_bytes"))
        #expect(unknownFields.contains("estimated_disk_usage_bytes"))
        #expect(unknownFields.contains("fit_status"))
        #expect(unknownFields.contains("parameter_count"))
        #expect(unknownFields.contains("quantization_summary"))
    }

    @Test("model download forwards the expected download operation payload")
    func modelDownloadForwardsExpectedOperationPayload() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(
            makeModelOperationResult(outputPath: "/tmp/melix-downloads/melix-dev-text")
        )

        let output = try await MelixCLIRunner(client: client).run(
            .modelDownload(
                .init(
                    modelID: "melix-dev-text",
                    outputDir: "/tmp/melix-downloads/melix-dev-text"
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(output == "/tmp/melix-downloads/melix-dev-text\n")
        #expect(call.modelID == "melix-dev-text")
        #expect(call.operation == "download")
        #expect(call.ext.isEmpty)
    }

    @Test("doctor command renders markdown and structured json payloads")
    func doctorCommandRendersMarkdownAndStructuredJSONPayloads() async throws {
        let client = StubControlPlaneXPCClient()
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-doctor-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        await client.setDoctorReport(
            makeDoctorReport(
                markdown: "# Melix Doctor\n\n- worker_state: idle\n",
                healthStatus: .healthy,
                findings: [
                    ("cache_warning", .warning, "Cache pressure", "Cache usage crossed the warning threshold."),
                ]
            )
        )

        let textOutput = try await MelixCLIRunner(client: client).run(.doctor(.init()))
        let jsonOutput = try await MelixCLIRunner(
            client: client,
            environment: [
                "MELIX_HOME": root.path,
                "MELIX_API_KEY": "sk-secret-doctor",
            ]
        ).run(.doctor(.init(json: true)))
        let payload = try #require(parseJSONObject(jsonOutput))
        let findings = try #require(payload["findings"] as? [[String: Any]])

        #expect(textOutput.contains("# Melix Doctor"))
        #expect(payload["markdown"] as? String == "# Melix Doctor\n\n- worker_state: idle\n")
        #expect(payload["health_status"] as? String == "healthy")
        #expect(payload["diagnostics_consent_state"] as? String == "local_only")
        #expect(payload["redaction_schema_version"] as? String == MelixDiagnosticsRedaction.schemaVersion)
        #expect((payload["redacted_field_count"] as? Int ?? 0) >= 1)
        #expect(findings.count >= 1)
        #expect(findings[0]["code"] as? String == "cache_warning")
        #expect(findings[0]["severity"] as? String == "warning")
    }

    @Test("json v1 wraps command results in a stable envelope")
    func jsonV1WrapsCommandResultsInAStableEnvelope() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setDoctorReport(
            makeDoctorReport(
                markdown: "# Melix Doctor\n\n- worker_state: idle\n",
                healthStatus: .healthy
            )
        )

        let output = try await MelixCLIRunner(client: client).run(
            MelixCLIInvocation(
                command: .doctor(.init()),
                outputFormat: .jsonV1,
                traceID: "trace-json-v1"
            )
        )
        let envelope = try #require(parseJSONObject(output))
        let result = try #require(envelope["result"] as? [String: Any])
        let metrics = try #require(envelope["metrics"] as? [String: Any])

        #expect(envelope["schema_version"] as? String == "melix.cli.output.v1")
        #expect(envelope["command_id"] as? String == "doctor")
        #expect(envelope["status"] as? String == "succeeded")
        #expect(envelope["trace_id"] as? String == "trace-json-v1")
        #expect(result["health_status"] as? String == "healthy")
        #expect((metrics["melix.cli.parse_ms"] as? Double) != nil)
        #expect((metrics["melix.cli.command_ms"] as? Double) != nil)
        #expect((metrics["melix.cli.json_encode_ms"] as? Double) != nil)

        let paddedJSON = try #require(MelixCLIJSON.jsonValue(from: "  {\"health_status\":\"healthy\"}\n") as? [String: Any])
        let fallbackText = try #require(MelixCLIJSON.jsonValue(from: "  plain text\n") as? [String: String])
        #expect(paddedJSON["health_status"] as? String == "healthy")
        #expect(fallbackText["text"] == "plain text")
    }

    @Test("json v1 error envelopes are machine readable")
    func jsonV1ErrorEnvelopesAreMachineReadable() throws {
        let output = try MelixCLIJSONEnvelope.errorEnvelopeString(
            commandID: "chat.run",
            traceID: "trace-error",
            error: MelixCLIError.missingRequired("--message is required for melix chat run."),
            metrics: ["melix.cli.parse_ms": 0.25]
        )
        let envelope = try #require(parseJSONObject(output))
        let error = try #require(envelope["error"] as? [String: Any])
        let metrics = try #require(envelope["metrics"] as? [String: Any])

        #expect(envelope["schema_version"] as? String == "melix.cli.error.v1")
        #expect(envelope["command_id"] as? String == "chat.run")
        #expect(envelope["status"] as? String == "failed")
        #expect(envelope["trace_id"] as? String == "trace-error")
        #expect(error["code"] as? String == "missing_required")
        #expect(error["message"] as? String == "--message is required for melix chat run.")
        #expect(metrics["melix.cli.parse_ms"] as? Double == 0.25)
    }

    @Test("settings show resolves precedence and reports source metadata")
    func settingsShowResolvesPrecedenceAndReportsSourceMetadata() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let projectRoot = root.appendingPathComponent("project", isDirectory: true)
        let melixHome = root.appendingPathComponent("home", isDirectory: true)
        try FileManager.default.createDirectory(at: projectRoot.appendingPathComponent(".melix", isDirectory: true), withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: melixHome, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        try writeJSONObjectForTest(
            [
                "model_cache_path": "/user/models",
                "max_concurrent_jobs": 2,
                "benchmark_repeats": 1,
            ],
            to: melixHome.appendingPathComponent("runtime_settings.json")
        )
        try writeJSONObjectForTest(
            [
                "max_concurrent_jobs": 4,
                "artifact_path": "/project/artifacts",
            ],
            to: projectRoot
                .appendingPathComponent(".melix", isDirectory: true)
                .appendingPathComponent("runtime_settings.json")
        )

        let output = try await MelixCLIRunner(
            client: StubControlPlaneXPCClient(),
            environment: [
                "MELIX_HOME": melixHome.path,
                "MELIX_PROJECT_ROOT": projectRoot.path,
                "MELIX_MAX_CONCURRENT_JOBS": "6",
            ]
        ).run(.settingsShow(.init(json: true, overrides: ["max_concurrent_jobs": "8"])))
        let payload = try #require(parseJSONObject(output))
        let settings = try #require(payload["settings"] as? [String: Any])
        let maxJobs = try #require(settings["max_concurrent_jobs"] as? [String: Any])
        let artifactPath = try #require(settings["artifact_path"] as? [String: Any])
        let modelCache = try #require(settings["model_cache_path"] as? [String: Any])
        let metrics = try #require(payload["metrics"] as? [String: Any])

        #expect(payload["schema_version"] as? String == "melix.runtime_settings.effective.v1")
        #expect((maxJobs["value"] as? NSNumber)?.intValue == 8)
        #expect(maxJobs["source"] as? String == "cli_flag")
        #expect(maxJobs["source_detail"] as? String == "--override max_concurrent_jobs")
        #expect(artifactPath["value"] as? String == "/project/artifacts")
        #expect(artifactPath["source"] as? String == "project_settings")
        #expect(modelCache["value"] as? String == "/user/models")
        #expect(modelCache["source"] as? String == "user_settings")
        #expect((metrics["settings_resolve_ms"] as? NSNumber)?.doubleValue ?? -1 >= 0)
    }

    @Test("settings set validate and reset mutate only the user settings file")
    func settingsSetValidateAndResetMutateOnlyUserSettingsFile() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let projectRoot = root.appendingPathComponent("project", isDirectory: true)
        let melixHome = root.appendingPathComponent("home", isDirectory: true)
        try FileManager.default.createDirectory(at: projectRoot, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: melixHome, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let runner = MelixCLIRunner(
            client: StubControlPlaneXPCClient(),
            environment: [
                "MELIX_HOME": melixHome.path,
                "MELIX_PROJECT_ROOT": projectRoot.path,
            ]
        )

        let setOutput = try await runner.run(.settingsSet(.init(key: "eval_sample_size", value: "25", json: true)))
        let setPayload = try #require(parseJSONObject(setOutput))
        #expect(setPayload["key"] as? String == "eval_sample_size")
        #expect((setPayload["value"] as? NSNumber)?.intValue == 25)
        #expect(setPayload["source"] as? String == "user_settings")

        let validateOutput = try await runner.run(.settingsValidate(.init(json: true)))
        let validatePayload = try #require(parseJSONObject(validateOutput))
        let metrics = try #require(validatePayload["metrics"] as? [String: Any])
        #expect(validatePayload["valid"] as? Bool == true)
        #expect((metrics["settings_validate_ms"] as? NSNumber)?.doubleValue ?? -1 >= 0)

        let resetOutput = try await runner.run(.settingsReset(.init(key: "eval_sample_size", json: true)))
        let resetPayload = try #require(parseJSONObject(resetOutput))
        #expect(resetPayload["removed"] as? Bool == true)

        let showOutput = try await runner.run(.settingsShow(.init(json: true)))
        let showPayload = try #require(parseJSONObject(showOutput))
        let settings = try #require(showPayload["settings"] as? [String: Any])
        let evalSampleSize = try #require(settings["eval_sample_size"] as? [String: Any])
        #expect(evalSampleSize["source"] as? String == "default")
    }

    @Test("settings validation reports invalid documents keys and values")
    func settingsValidationReportsInvalidDocumentsKeysAndValues() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let projectRoot = root.appendingPathComponent("project", isDirectory: true)
        let projectSettingsDir = projectRoot.appendingPathComponent(".melix", isDirectory: true)
        let melixHome = root.appendingPathComponent("home", isDirectory: true)
        try FileManager.default.createDirectory(at: projectSettingsDir, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: melixHome, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        try writeJSONObjectForTest(
            [
                "max_concurrent_jobs": "many",
                "unknown_setting": true,
            ],
            to: melixHome.appendingPathComponent("runtime_settings.json")
        )
        try Data("[1,2,3]".utf8).write(
            to: projectSettingsDir.appendingPathComponent("runtime_settings.json")
        )

        let runner = MelixCLIRunner(
            client: StubControlPlaneXPCClient(),
            environment: [
                "MELIX_HOME": melixHome.path,
                "MELIX_PROJECT_ROOT": projectRoot.path,
            ]
        )
        let output = try await runner.run(.settingsValidate(.init(json: true)))
        let payload = try #require(parseJSONObject(output))
        let errors = try #require(payload["errors"] as? [[String: Any]])

        #expect(payload["valid"] as? Bool == false)
        #expect(errors.contains { $0["key"] as? String == "max_concurrent_jobs" })
        #expect(errors.contains { $0["key"] as? String == "unknown_setting" })
        #expect(errors.contains { ($0["message"] as? String)?.contains("invalidDocument") == true })
    }

    @Test("settings mutation commands reject unknown keys invalid values and malformed stores")
    func settingsMutationCommandsRejectUnknownKeysInvalidValuesAndMalformedStores() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let projectRoot = root.appendingPathComponent("project", isDirectory: true)
        let melixHome = root.appendingPathComponent("home", isDirectory: true)
        try FileManager.default.createDirectory(at: projectRoot, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: melixHome, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let environment = [
            "MELIX_HOME": melixHome.path,
            "MELIX_PROJECT_ROOT": projectRoot.path,
        ]
        let runner = MelixCLIRunner(client: StubControlPlaneXPCClient(), environment: environment)

        await #expect(throws: MelixRuntimeSettingsError.unknownKey("missing_key")) {
            _ = try await runner.run(.settingsSet(.init(key: "missing_key", value: "1", json: true)))
        }
        await #expect(throws: MelixRuntimeSettingsError.invalidValue(key: "max_concurrent_jobs", expectedType: "int", value: "many")) {
            _ = try await runner.run(.settingsSet(.init(key: "max_concurrent_jobs", value: "many", json: true)))
        }
        await #expect(throws: MelixRuntimeSettingsError.invalidValue(key: "max_concurrent_jobs", expectedType: "int", value: "2.5")) {
            _ = try await runner.run(.settingsSet(.init(key: "max_concurrent_jobs", value: "2.5", json: true)))
        }
        await #expect(throws: MelixRuntimeSettingsError.unknownKey("missing_key")) {
            _ = try await runner.run(.settingsReset(.init(key: "missing_key", json: true)))
        }

        let settingsPath = melixHome.appendingPathComponent("runtime_settings.json")
        try Data("[1,2,3]".utf8).write(to: settingsPath)
        await #expect(throws: MelixRuntimeSettingsError.invalidDocument(path: settingsPath.path)) {
            _ = try await runner.run(.settingsShow(.init(json: true)))
        }
    }

    @Test("info discovery reads local update channel receipts without network")
    func infoDiscoveryReadsLocalUpdateChannelReceiptsWithoutNetwork() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let projectRoot = root.appendingPathComponent("project", isDirectory: true)
        let melixHome = root.appendingPathComponent("home", isDirectory: true)
        let channelPath = root.appendingPathComponent("channel.json")
        try FileManager.default.createDirectory(at: projectRoot, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: melixHome, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        try writeJSONObjectForTest(
            [
                "latest_known_version": "999.0.0",
                "update_channel": "nightly",
            ],
            to: channelPath
        )

        let output = try await MelixCLIRunner(
            client: StubControlPlaneXPCClient(),
            environment: [
                "MELIX_HOME": melixHome.path,
                "MELIX_PROJECT_ROOT": projectRoot.path,
                "MELIX_UPDATE_CHANNEL_PATH": channelPath.path,
                "MELIX_INSTALL_METHOD": "homebrew",
            ]
        ).run(.info(.init(json: true)))
        let payload = try #require(parseJSONObject(output))
        let update = try #require(payload["update"] as? [String: Any])

        #expect(update["status"] as? String == "ok")
        #expect(update["latest_known_version"] as? String == "999.0.0")
        #expect(update["update_available"] as? Bool == true)
        #expect(update["update_channel"] as? String == "nightly")
        #expect(update["install_method"] as? String == "homebrew")
        #expect(update["suggested_update_command"] as? [String] == [])
    }

    @Test("discovery commands expose machine readable info capabilities instructions schema and config metadata")
    func discoveryCommandsExposeMachineReadablePayloads() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let projectRoot = root.appendingPathComponent("project", isDirectory: true)
        let melixHome = root.appendingPathComponent("home", isDirectory: true)
        try FileManager.default.createDirectory(at: projectRoot, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: melixHome, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let runner = MelixCLIRunner(
            client: StubControlPlaneXPCClient(),
            environment: [
                "MELIX_HOME": melixHome.path,
                "MELIX_PROJECT_ROOT": projectRoot.path,
                "MELIX_UPDATE_CHANNEL_PATH": root.appendingPathComponent("missing-channel.json").path,
            ]
        )

        let info = try #require(parseJSONObject(try await runner.run(.info(.init(json: true)))))
        let update = try #require(info["update"] as? [String: Any])
        let localPaths = try #require(info["local_paths"] as? [String: Any])
        let infoMetrics = try #require(info["metrics"] as? [String: Any])
        #expect(info["schema_version"] as? String == "melix.discovery.info.v1")
        #expect(update["installed_version"] as? String != nil)
        #expect(update["latest_known_version"] as? String == "")
        #expect(update["install_method"] as? String != nil)
        #expect(update["suggested_update_command"] as? [String] != nil)
        #expect(update["status"] as? String == "unavailable")
        #expect(localPaths["melix_home"] as? String == melixHome.path)
        let projectSettingsPath = projectRoot
            .appendingPathComponent(".melix", isDirectory: true)
            .appendingPathComponent("runtime_settings.json")
            .path
        #expect(localPaths["project_settings"] as? String == projectSettingsPath)
        #expect((infoMetrics["discovery_build_ms"] as? NSNumber)?.doubleValue ?? -1 >= 0)

        let capabilities = try #require(parseJSONObject(try await runner.run(.capabilities(.init(json: true, modelQuery: "qwen35_9b_mlx_4bit")))))
        let alias = try #require(capabilities["model_alias_discovery"] as? [String: Any])
        let suggestions = try #require(alias["suggestions"] as? [[String: Any]])
        #expect(capabilities["schema_version"] as? String == "melix.discovery.capabilities.v1")
        #expect((capabilities["supported_tasks"] as? [String])?.contains("text-generation") == true)
        #expect(suggestions.contains { $0["model_id"] as? String == "mlx-community/Qwen3.5-9B-MLX-4bit" })

        let fullIDCapabilities = try #require(parseJSONObject(try await runner.run(.capabilities(.init(json: true, modelQuery: "mlx-community/Qwen3.5-9B-MLX-4bit")))))
        let fullIDAlias = try #require(fullIDCapabilities["model_alias_discovery"] as? [String: Any])
        #expect(fullIDAlias["status"] as? String == "valid_full_model_id")
        #expect((fullIDAlias["suggestions"] as? [[String: Any]])?.isEmpty == true)

        let localPathCapabilities = try #require(parseJSONObject(try await runner.run(.capabilities(.init(json: true, modelQuery: "/tmp/local-model")))))
        let localPathAlias = try #require(localPathCapabilities["model_alias_discovery"] as? [String: Any])
        #expect(localPathAlias["status"] as? String == "local_path_passthrough")
        #expect((localPathAlias["suggestions"] as? [[String: Any]])?.isEmpty == true)

        for query in ["~/local-model", "./local-model", "../local-model", "file:///tmp/local-model"] {
            let payload = try #require(parseJSONObject(try await runner.run(.capabilities(.init(json: true, modelQuery: query)))))
            let alias = try #require(payload["model_alias_discovery"] as? [String: Any])
            #expect(alias["status"] as? String == "local_path_passthrough")
        }

        let notRequestedCapabilities = try #require(parseJSONObject(try await runner.run(.capabilities(.init(json: true)))))
        let notRequestedAlias = try #require(notRequestedCapabilities["model_alias_discovery"] as? [String: Any])
        #expect(notRequestedAlias["status"] as? String == "not_requested")

        let noMatchCapabilities = try #require(parseJSONObject(try await runner.run(.capabilities(.init(json: true, modelQuery: "not a/model id")))))
        let noMatchAlias = try #require(noMatchCapabilities["model_alias_discovery"] as? [String: Any])
        #expect(noMatchAlias["status"] as? String == "no_match")

        let qwen8BitCapabilities = try #require(parseJSONObject(try await runner.run(.capabilities(.init(json: true, modelQuery: "qwen35_9b_mlx_8bit")))))
        let qwen8BitAlias = try #require(qwen8BitCapabilities["model_alias_discovery"] as? [String: Any])
        let qwen8BitSuggestions = try #require(qwen8BitAlias["suggestions"] as? [[String: Any]])
        #expect(qwen8BitSuggestions.contains { $0["model_id"] as? String == "mlx-community/Qwen3.5-9B-MLX-8bit" })

        let qwen26BCapabilities = try #require(parseJSONObject(try await runner.run(.capabilities(.init(json: true, modelQuery: "qwen35_26b_mlx_4bit")))))
        let qwen26BAlias = try #require(qwen26BCapabilities["model_alias_discovery"] as? [String: Any])
        let qwen26BSuggestions = try #require(qwen26BAlias["suggestions"] as? [[String: Any]])
        #expect(qwen26BSuggestions.contains { $0["model_id"] as? String == "mlx-community/Qwen3.5-26B-MLX-4bit" })

        let instructions = try #require(parseJSONObject(try await runner.run(.instructions(.init(json: true)))))
        #expect(instructions["schema_version"] as? String == "melix.discovery.instructions.v1")
        #expect((instructions["areas"] as? [[String: Any]])?.contains { $0["id"] as? String == "settings" } == true)

        let schema = try #require(parseJSONObject(try await runner.run(.schema(.init(json: true)))))
        #expect(schema["schema_version"] as? String == "melix.discovery.schema.v1")
        #expect((schema["schemas"] as? [[String: Any]])?.contains { ($0["path"] as? String)?.contains("packages/protocol/schema") == true } == true)

        let metadata = try #require(parseJSONObject(try await runner.run(.configMetadata(.init(json: true)))))
        #expect(metadata["schema_version"] as? String == "melix.discovery.config_metadata.v1")
        #expect((metadata["settings"] as? [[String: Any]])?.contains { $0["key"] as? String == "memory_pressure_threshold" } == true)
    }

    @Test("json metric patching rejects missing placeholders")
    func jsonMetricPatchingRejectsMissingPlaceholders() throws {
        #expect(throws: MelixCLIError.runtime("Failed to encode CLI metrics placeholder.")) {
            try MelixCLIJSONMetricPatch.replacePlaceholder(in: "{}", with: 1)
        }
        #expect(throws: MelixCLIError.runtime("Failed to locate pipeline metrics placeholder.")) {
            try MelixCLIJSONMetricPatch.placeholderRange(in: Data("{}".utf8))
        }
        let duplicatePlaceholder = MelixCLIJSONMetricPatch.Placeholder(token: "__DUPLICATE__")
        #expect(throws: MelixCLIError.runtime("Found duplicate CLI metrics placeholders.")) {
            try MelixCLIJSONMetricPatch.replacePlaceholder(
                in: "\(duplicatePlaceholder.jsonLiteral) \(duplicatePlaceholder.jsonLiteral)",
                placeholder: duplicatePlaceholder,
                with: 1
            )
        }
        #expect(throws: MelixCLIError.runtime("Found duplicate pipeline metrics placeholders.")) {
            try MelixCLIJSONMetricPatch.placeholderRange(
                in: Data("\(duplicatePlaceholder.jsonLiteral) \(duplicatePlaceholder.jsonLiteral)".utf8),
                placeholder: duplicatePlaceholder
            )
        }
        #expect(throws: MelixCLIError.runtime("Pipeline metrics placeholder is too short for the encoded metric.")) {
            try MelixCLIJSONMetricPatch.paddedLiteralData(for: 1, byteCount: 1)
        }
        #expect(MelixCLIJSONMetricPatch.literal(for: 1.5) == "1.5000000000000000e+00")
        #expect(MelixCLIJSONMetricPatch.literal(for: -1) == "0.0000000000000000e+00")
    }

    @Test("batch run dry-run writes effective config and manifest artifacts")
    func batchRunDryRunWritesEffectiveConfigAndManifestArtifacts() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let modelList = root.appendingPathComponent("models.txt")
        let tempRoot = root.appendingPathComponent("tmp-run")
        let outputRoot = root.appendingPathComponent("downloads")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try """
        # preserve comments and duplicates
        mlx-community/Qwen3.5-9B-MLX-4bit
        07|unsloth/Qwen3.6-27B-UD-MLX-4bit
        08|unsloth/Qwen3.6-27B-UD-MLX-4bit
        """.write(to: modelList, atomically: true, encoding: .utf8)

        let runner = MelixCLIRunner(environment: ["HOME": root.path])
        let output = try await runner.run(.batchRun(.init(
            modelListPath: modelList.path,
            runID: "dry-run-1",
            outputRoot: outputRoot.path,
            tempRoot: tempRoot.path,
            startIndex: 2,
            maxModels: 1,
            dryRun: true
        )))

        #expect(output.contains("Melix batch run dry-run"))
        #expect(output.contains("models=1/3"))
        #expect(output.contains("[1/1] PLAN 07 unsloth/Qwen3.6-27B-UD-MLX-4bit"))

        let effectiveConfigPath = tempRoot.appendingPathComponent("effective-config.json")
        let manifestPath = tempRoot.appendingPathComponent("manifest.jsonl")
        let copiedConfigPath = outputRoot.appendingPathComponent("effective-config.json")
        let copiedManifestPath = outputRoot.appendingPathComponent("manifest.jsonl")
        #expect(FileManager.default.fileExists(atPath: effectiveConfigPath.path))
        #expect(FileManager.default.fileExists(atPath: manifestPath.path))
        #expect(FileManager.default.fileExists(atPath: copiedConfigPath.path))
        #expect(FileManager.default.fileExists(atPath: copiedManifestPath.path))

        let effectiveConfig = try #require(try parseJSONFile(effectiveConfigPath.path))
        #expect(effectiveConfig["schema_version"] as? String == "melix.batch.effective_config.v1")
        #expect(effectiveConfig["run_id"] as? String == "dry-run-1")
        #expect(effectiveConfig["selected_model_count"] as? Int == 1)
        #expect(effectiveConfig["total_model_count"] as? Int == 3)
        #expect(effectiveConfig["is_subset_run"] as? Bool == true)
        #expect(effectiveConfig["preflight"] as? Bool == false)
        let isolationPolicy = try #require(effectiveConfig["isolation_policy"] as? [String: Any])
        #expect(isolationPolicy["best_effort_unload_previous_model"] as? Bool == true)
        #expect(isolationPolicy["force_clean_stack_after_runtime_failure"] as? Bool == true)
        let models = try #require(effectiveConfig["models"] as? [[String: Any]])
        #expect(models.count == 1)
        #expect(models[0]["index"] as? String == "07")
        #expect(models[0]["repo_id"] as? String == "unsloth/Qwen3.6-27B-UD-MLX-4bit")

        let manifest = try String(contentsOf: manifestPath, encoding: .utf8)
        let manifestLines = manifest.split(separator: "\n")
        #expect(manifestLines.count == 1)
        let manifestEntry = try #require(parseJSONObject(String(manifestLines[0])))
        #expect(manifestEntry["status"] as? String == "planned")
        #expect(manifestEntry["model_index"] as? String == "07")
        #expect(manifestEntry["repo_id"] as? String == "unsloth/Qwen3.6-27B-UD-MLX-4bit")
        #expect(manifestEntry["failure_category"] as? String == "")
        #expect(manifestEntry["recoverability"] as? String == "")
        let steps = try #require(manifestEntry["steps"] as? [String: Any])
        #expect(steps["preflight"] != nil)
        #expect(steps["runtime_prepare"] != nil)
        #expect(steps["model_unload"] != nil)
    }

    @Test("batch run dry-run start index is positional")
    func batchRunDryRunStartIndexIsPositional() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let modelList = root.appendingPathComponent("models.txt")
        let tempRoot = root.appendingPathComponent("tmp-run")
        let outputRoot = root.appendingPathComponent("downloads")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try """
        A|mlx-community/Alpha-4bit
        10|mlx-community/Ten-4bit
        20|mlx-community/Twenty-4bit
        """.write(to: modelList, atomically: true, encoding: .utf8)

        let runner = MelixCLIRunner(environment: ["HOME": root.path])
        _ = try await runner.run(.batchRun(.init(
            modelListPath: modelList.path,
            runID: "dry-run-positional",
            outputRoot: outputRoot.path,
            tempRoot: tempRoot.path,
            startIndex: 2,
            maxModels: 1,
            dryRun: true
        )))

        let effectiveConfig = try #require(try parseJSONFile(tempRoot.appendingPathComponent("effective-config.json").path))
        let models = try #require(effectiveConfig["models"] as? [[String: Any]])
        #expect(models.count == 1)
        #expect(models[0]["index"] as? String == "10")
        #expect(models[0]["repo_id"] as? String == "mlx-community/Ten-4bit")
    }

    @Test("batch model-list parser rejects invalid lines")
    func batchModelListParserRejectsInvalidLines() throws {
        #expect(throws: MelixCLIError.usage("Empty model index at 2.")) {
            _ = try BatchRunModelListParser.parse(contents: "mlx-community/Valid-4bit\n  |mlx-community/MissingIndex-4bit\n")
        }
        #expect(throws: MelixCLIError.usage("Empty repo id at 2.")) {
            _ = try BatchRunModelListParser.parse(contents: "mlx-community/Valid-4bit\n42|\n")
        }
        #expect(throws: MelixCLIError.usage("Empty model index at 1.")) {
            _ = try BatchRunModelListParser.parse(contents: "|\n")
        }
        #expect(throws: MelixCLIError.usage("Empty model index at 1.")) {
            _ = try BatchRunModelListParser.parse(contents: "|")
        }
    }

    @Test("batch model-list parser comments do not consume auto indexes")
    func batchModelListParserCommentsDoNotConsumeAutoIndexes() throws {
        let entries = try BatchRunModelListParser.parse(contents: """
        mlx-community/Alpha-4bit
        # comment
        mlx-community/Beta-4bit
        """)
        #expect(entries.map(\.index) == ["01", "02"])
        #expect(entries.map(\.repoID) == ["mlx-community/Alpha-4bit", "mlx-community/Beta-4bit"])
        #expect(entries.map(\.sourceLine) == [1, 3])
    }

    @Test("batch run dry-run supports matching temp and output roots")
    func batchRunDryRunSupportsMatchingTempAndOutputRoots() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let modelList = root.appendingPathComponent("models.txt")
        let runRoot = root.appendingPathComponent("same-root")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try """
        mlx-community/Qwen3.5-9B-MLX-4bit
        """.write(to: modelList, atomically: true, encoding: .utf8)

        let runner = MelixCLIRunner(environment: ["HOME": root.path])
        _ = try await runner.run(.batchRun(.init(
            modelListPath: modelList.path,
            runID: "dry-run-same-root",
            outputRoot: runRoot.path,
            tempRoot: runRoot.path,
            dryRun: true
        )))

        let effectiveConfigPath = runRoot.appendingPathComponent("effective-config.json")
        let manifestPath = runRoot.appendingPathComponent("manifest.jsonl")
        #expect(FileManager.default.fileExists(atPath: effectiveConfigPath.path))
        #expect(FileManager.default.fileExists(atPath: manifestPath.path))
        let manifest = try String(contentsOf: manifestPath, encoding: .utf8)
        #expect(manifest.split(separator: "\n").count == 1)
    }

    @Test("batch run dry-run explicit CLI defaults override config")
    func batchRunDryRunExplicitCLIDefaultsOverrideConfig() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let modelList = root.appendingPathComponent("models.txt")
        let config = root.appendingPathComponent("batch.yaml")
        let tempRoot = root.appendingPathComponent("tmp-run")
        let outputRoot = root.appendingPathComponent("downloads")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try """
        mlx-community/Qwen3.5-9B-MLX-4bit
        07|unsloth/Qwen3.6-27B-UD-MLX-4bit
        08|unsloth/Qwen3.6-27B-UD-MLX-4bit
        """.write(to: modelList, atomically: true, encoding: .utf8)
        try """
        max_models: 1
        continue_on_failure: false
        restart_stack_per_model: false
        bench_sample_size: 9
        """.write(to: config, atomically: true, encoding: .utf8)

        let command = try MelixCLIParser.parse([
            "batch", "run",
            "--models", modelList.path,
            "--config", config.path,
            "--run-id", "dry-run-precedence",
            "--output-root", outputRoot.path,
            "--temp-root", tempRoot.path,
            "--max-models", "0",
            "--continue-on-failure", "true",
            "--restart-stack-per-model", "true",
            "--bench-sample-size", "1",
            "--dry-run",
        ])
        let runner = MelixCLIRunner(environment: ["HOME": root.path])
        _ = try await runner.run(command)

        let effectiveConfig = try #require(try parseJSONFile(tempRoot.appendingPathComponent("effective-config.json").path))
        #expect(effectiveConfig["selected_model_count"] as? Int == 3)
        #expect(effectiveConfig["max_models"] as? Int == 0)
        #expect(effectiveConfig["continue_on_failure"] as? Bool == true)
        #expect(effectiveConfig["restart_stack_per_model"] as? Bool == true)
        let benchmark = try #require(effectiveConfig["benchmark"] as? [String: Any])
        #expect(benchmark["sample_size"] as? Int == 1)
    }

    @Test("batch run dry-run preflight writes readiness report")
    func batchRunDryRunPreflightWritesReadinessReport() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let repoRoot = root.appendingPathComponent("repo")
        let cliPath = repoRoot.appendingPathComponent(".build/debug/melix")
        let fixtureRoot = repoRoot
            .appendingPathComponent("services/mlx-worker-python/fixtures/evaluation/top200.event-extraction.top20.v1", isDirectory: true)
        let melixHome = root.appendingPathComponent("home")
        let modelList = root.appendingPathComponent("models.txt")
        let tempRoot = root.appendingPathComponent("tmp-run")
        let outputRoot = root.appendingPathComponent("downloads")
        try FileManager.default.createDirectory(at: cliPath.deletingLastPathComponent(), withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: fixtureRoot, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: melixHome, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try "#!/usr/bin/env bash\n".write(to: cliPath, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: cliPath.path)
        let controlPlanePath = repoRoot.appendingPathComponent(".build/debug/MelixControlPlaneService")
        try "#!/usr/bin/env bash\n".write(to: controlPlanePath, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: controlPlanePath.path)
        try FileManager.default.createDirectory(
            at: repoRoot.appendingPathComponent("services/mlx-worker-python/worker", isDirectory: true),
            withIntermediateDirectories: true
        )
        try "{}\n".write(to: fixtureRoot.appendingPathComponent("manifest.json"), atomically: true, encoding: .utf8)
        try "{}\n".write(to: fixtureRoot.appendingPathComponent("samples.jsonl"), atomically: true, encoding: .utf8)
        try "mlx-community/Qwen3.5-9B-MLX-4bit\n".write(to: modelList, atomically: true, encoding: .utf8)

        let runner = MelixCLIRunner(environment: [
            "HOME": root.path,
            "MELIX_REPO_ROOT": repoRoot.path,
            "MELIX_HOME": melixHome.path,
            "MELIX_CLI": cliPath.path,
            "MELIX_HTTP_PORT": "12444",
        ])
        _ = try await runner.run(
            .remoteServerAdd(
                .init(
                    remoteServerID: "judge",
                    title: "Judge",
                    providerPreset: .custom,
                    providerKind: "openai-compatible",
                    baseURL: "https://judge.example/v1",
                    defaultModelID: "gpt-test",
                    apiKey: "sk-test-secret",
                    json: true
                )
            )
        )

        let output = try await runner.run(.batchRun(.init(
            modelListPath: modelList.path,
            runID: "preflight-ok",
            outputRoot: outputRoot.path,
            tempRoot: tempRoot.path,
            judgeRemoteServerID: "judge",
            judgeModelID: "gpt-test",
            preflight: true,
            dryRun: true
        )))

        #expect(output.contains("preflight_status=ready"))
        #expect(output.contains("CHECK judge ready"))
        #expect(output.contains("melix_home=\(melixHome.path)"))

        let reportPath = tempRoot.appendingPathComponent("preflight-report.json")
        let copiedReportPath = outputRoot.appendingPathComponent("preflight-report.json")
        #expect(FileManager.default.fileExists(atPath: reportPath.path))
        #expect(FileManager.default.fileExists(atPath: copiedReportPath.path))
        let report = try #require(try parseJSONFile(reportPath.path))
        #expect(report["schema_version"] as? String == "melix.batch.preflight_report.v1")
        #expect(report["status"] as? String == "ready")
        #expect(report["blocker_count"] as? Int == 0)
        let runtime = try #require(report["runtime"] as? [String: Any])
        #expect(runtime["melix_home"] as? String == melixHome.path)
        let checks = try #require(report["checks"] as? [[String: Any]])
        let checkByName = Dictionary(uniqueKeysWithValues: checks.compactMap { check -> (String, [String: Any])? in
            guard let name = check["name"] as? String else {
                return nil
            }
            return (name, check)
        })
        let isolatedRuntimeCheck = try #require(checkByName["isolated_runtime_config"])
        #expect(isolatedRuntimeCheck["status"] as? String == "ready")
        let isolatedMetadata = try #require(isolatedRuntimeCheck["metadata"] as? [String: Any])
        #expect(isolatedMetadata["bare_default_ports"] as? String == "11434,12436")
        let controlPlaneCheck = try #require(checkByName["control_plane"])
        #expect(controlPlaneCheck["status"] as? String == "ready")
        #expect((try #require(controlPlaneCheck["metadata"] as? [String: Any]))["requires_executable"] as? String == "true")
        let modelCheck = try #require(checkByName["model_repo:01"])
        #expect(modelCheck["status"] as? String == "ready")
        #expect(modelCheck["category"] as? String == "model_resolution")
        let modelMetadata = try #require(modelCheck["metadata"] as? [String: Any])
        #expect(modelMetadata["duplicate_count"] as? String == "1")
        let cacheCheck = try #require(checkByName["cache_state"])
        #expect(cacheCheck["category"] as? String == "cache")
        let datasetCheck = try #require(checkByName["dataset"])
        #expect(datasetCheck["category"] as? String == "dataset")
        #expect((try #require(datasetCheck["metadata"] as? [String: Any]))["source"] as? String == "repo_fixture")
        let judgeCheck = try #require(checkByName["judge"])
        #expect(judgeCheck["category"] as? String == "judge")
        #expect((try #require(judgeCheck["metadata"] as? [String: Any]))["model_id"] as? String == "gpt-test")

        let effectiveConfig = try #require(try parseJSONFile(tempRoot.appendingPathComponent("effective-config.json").path))
        #expect(effectiveConfig["preflight"] as? Bool == true)
        #expect(effectiveConfig["preflight_report"] as? String == reportPath.path)
    }

    @Test("batch run dry-run preflight blocks missing judge before sweep")
    func batchRunDryRunPreflightBlocksMissingJudgeBeforeSweep() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let repoRoot = root.appendingPathComponent("repo")
        let cliPath = repoRoot.appendingPathComponent(".build/debug/melix")
        let fixtureRoot = repoRoot
            .appendingPathComponent("services/mlx-worker-python/fixtures/evaluation/top200.event-extraction.top20.v1", isDirectory: true)
        let melixHome = root.appendingPathComponent("home")
        let modelList = root.appendingPathComponent("models.txt")
        let tempRoot = root.appendingPathComponent("tmp-run")
        let outputRoot = root.appendingPathComponent("downloads")
        try FileManager.default.createDirectory(at: cliPath.deletingLastPathComponent(), withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: fixtureRoot, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: melixHome, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try "#!/usr/bin/env bash\n".write(to: cliPath, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: cliPath.path)
        let controlPlanePath = repoRoot.appendingPathComponent(".build/debug/MelixControlPlaneService")
        try "#!/usr/bin/env bash\n".write(to: controlPlanePath, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: controlPlanePath.path)
        try FileManager.default.createDirectory(
            at: repoRoot.appendingPathComponent("services/mlx-worker-python/worker", isDirectory: true),
            withIntermediateDirectories: true
        )
        try "{}\n".write(to: fixtureRoot.appendingPathComponent("manifest.json"), atomically: true, encoding: .utf8)
        try "{}\n".write(to: fixtureRoot.appendingPathComponent("samples.jsonl"), atomically: true, encoding: .utf8)
        try "mlx-community/Qwen3.5-9B-MLX-4bit\n".write(to: modelList, atomically: true, encoding: .utf8)

        let runner = MelixCLIRunner(environment: [
            "HOME": root.path,
            "MELIX_REPO_ROOT": repoRoot.path,
            "MELIX_HOME": melixHome.path,
            "MELIX_CLI": cliPath.path,
            "MELIX_HTTP_PORT": "12445",
        ])
        let message = try await requireRuntimeError {
            _ = try await runner.run(.batchRun(.init(
                modelListPath: modelList.path,
                runID: "preflight-blocked",
                outputRoot: outputRoot.path,
                tempRoot: tempRoot.path,
                judgeRemoteServerID: "missing-judge",
                preflight: true,
                dryRun: true
            )))
        }

        #expect(message.contains("Batch preflight blocked run preflight-blocked before execution."))
        #expect(message.contains("Remote server missing-judge was not found"))
        let report = try #require(try parseJSONFile(tempRoot.appendingPathComponent("preflight-report.json").path))
        #expect(report["status"] as? String == "blocked")
        #expect(report["blocker_count"] as? Int == 1)
        let checks = try #require(report["checks"] as? [[String: Any]])
        let judgeCheck = try #require(checks.first { $0["name"] as? String == "judge" })
        #expect(judgeCheck["category"] as? String == "judge")
        let metadata = try #require(judgeCheck["metadata"] as? [String: Any])
        #expect(metadata["remote_server_id"] as? String == "missing-judge")
        #expect(metadata["melix_home"] as? String == melixHome.path)
    }

    @Test("batch preflight blocks bare default batch port")
    func batchPreflightBlocksBareDefaultBatchPort() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let repoRoot = root.appendingPathComponent("repo")
        let cliPath = repoRoot.appendingPathComponent(".build/debug/melix")
        let fixtureRoot = repoRoot
            .appendingPathComponent("services/mlx-worker-python/fixtures/evaluation/top200.event-extraction.top20.v1", isDirectory: true)
        let melixHome = root.appendingPathComponent("home")
        let modelList = root.appendingPathComponent("models.txt")
        let tempRoot = root.appendingPathComponent("tmp-run")
        let outputRoot = root.appendingPathComponent("downloads")
        try FileManager.default.createDirectory(at: cliPath.deletingLastPathComponent(), withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: fixtureRoot, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: melixHome, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(
            at: repoRoot.appendingPathComponent("services/mlx-worker-python/worker", isDirectory: true),
            withIntermediateDirectories: true
        )
        defer { try? FileManager.default.removeItem(at: root) }
        try "#!/usr/bin/env bash\n".write(to: cliPath, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: cliPath.path)
        let controlPlanePath = repoRoot.appendingPathComponent(".build/debug/MelixControlPlaneService")
        try "#!/usr/bin/env bash\n".write(to: controlPlanePath, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: controlPlanePath.path)
        try "{}\n".write(to: fixtureRoot.appendingPathComponent("manifest.json"), atomically: true, encoding: .utf8)
        try "{}\n".write(to: fixtureRoot.appendingPathComponent("samples.jsonl"), atomically: true, encoding: .utf8)
        try "mlx-community/Qwen3.5-9B-MLX-4bit\n".write(to: modelList, atomically: true, encoding: .utf8)

        let runner = MelixCLIRunner(environment: [
            "HOME": root.path,
            "MELIX_REPO_ROOT": repoRoot.path,
            "MELIX_HOME": melixHome.path,
            "MELIX_CLI": cliPath.path,
        ])
        _ = try await runner.run(.remoteServerAdd(.init(
            remoteServerID: "judge",
            title: "Judge",
            providerPreset: .custom,
            providerKind: "openai-compatible",
            baseURL: "https://judge.example/v1",
            defaultModelID: "gpt-test",
            apiKey: "sk-test-secret",
            json: true
        )))

        let message = try await requireRuntimeError {
            _ = try await runner.run(.batchRun(.init(
                modelListPath: modelList.path,
                runID: "preflight-default-port",
                outputRoot: outputRoot.path,
                tempRoot: tempRoot.path,
                judgeRemoteServerID: "judge",
                judgeModelID: "gpt-test",
                preflight: true,
                dryRun: true
            )))
        }

        #expect(message.contains("batch mode must not use the bare default Melix stack"))
        let report = try #require(try parseJSONFile(tempRoot.appendingPathComponent("preflight-report.json").path))
        let checks = try #require(report["checks"] as? [[String: Any]])
        let isolatedRuntimeCheck = try #require(checks.first { $0["name"] as? String == "isolated_runtime_config" })
        #expect(isolatedRuntimeCheck["status"] as? String == "blocked")
        let metadata = try #require(isolatedRuntimeCheck["metadata"] as? [String: Any])
        #expect(metadata["http_port"] as? String == "12436")
        #expect(metadata["bare_default_ports"] as? String == "11434,12436")
    }

    @Test("batch failure classifier separates runtime and model failures")
    func batchFailureClassifierSeparatesRuntimeAndModelFailures() throws {
        let socket = BatchRunFailureClassifier.classify(stderr: #"requestFailed(code: "unavailable", message: "python-worker.sock: connect: Connection refused (61)")"#)
        #expect(socket.category == "worker_connectivity")
        #expect(socket.recoverability == .cleanRestartAndRetry)
        #expect(BatchRunFailureClassifier.runtimeFailureRequiresCleanStack(socket))

        let oom = BatchRunFailureClassifier.classify(stderr: "kIOGPUCommandBufferCallbackErrorOutOfMemory")
        #expect(oom.category == "metal_oom")
        #expect(oom.recoverability == .cleanRestartAndRetry)

        let target = BatchRunFailureClassifier.classify(stderr: "No loaded benchmark target is available for repo_id bad")
        #expect(target.category == "target_resolution")
        #expect(target.recoverability == .operatorActionRequired)

        let judge = BatchRunFailureClassifier.classify(stderr: "Semantic judge remote server returned 401 unauthorized")
        #expect(judge.category == "judge_failure")
        #expect(judge.recoverability == .operatorActionRequired)

        let export = BatchRunFailureClassifier.classify(stderr: "eval export-samples-jsonl failed: permission denied")
        #expect(export.category == "artifact_export")
        #expect(export.recoverability == .retrySameModel)

        let unknown = BatchRunFailureClassifier.classify(stderr: "unexpected model response")
        #expect(unknown.category == "unknown_failure")
        #expect(unknown.recoverability == .unknown)
    }

    @Test("batch run config rejects unsupported and raw secret keys")
    func batchRunConfigRejectsUnsupportedAndRawSecretKeys() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let modelList = root.appendingPathComponent("models.txt")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try "mlx-community/Qwen3.5-9B-MLX-4bit\n".write(to: modelList, atomically: true, encoding: .utf8)

        let unknownConfig = root.appendingPathComponent("unknown.yaml")
        try """
        model_list: \(modelList.path)
        unsupported_field: value
        """.write(to: unknownConfig, atomically: true, encoding: .utf8)

        let secretConfig = root.appendingPathComponent("secret.yaml")
        try """
        model_list: \(modelList.path)
        judge_api_key: sk-live-secret
        """.write(to: secretConfig, atomically: true, encoding: .utf8)

        let runner = MelixCLIRunner(environment: ["HOME": root.path])
        let unknownMessage = try await requireUsageError {
            _ = try await runner.run(.batchRun(.init(modelListPath: "", configPath: unknownConfig.path, dryRun: true)))
        }
        #expect(unknownMessage.starts(with: "Unsupported batch config key 'unsupported_field' at line 2."))
        #expect(unknownMessage.contains("Supported keys:"))
        #expect(unknownMessage.contains("model_list"))
        #expect(unknownMessage.contains("judge_remote_server_id"))

        let secretMessage = try await requireUsageError {
            _ = try await runner.run(.batchRun(.init(modelListPath: "", configPath: secretConfig.path, dryRun: true)))
        }
        #expect(secretMessage == "Unsupported batch config key 'judge_api_key' at line 2. Batch configs must reference stored credentials by id instead of embedding raw secrets.")
    }

    @Test("batch run executes benchmark evaluation exports and writes reports")
    func batchRunExecutesBenchmarkEvaluationExportsAndWritesReports() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let modelList = root.appendingPathComponent("models.txt")
        let tempRoot = root.appendingPathComponent("tmp-run")
        let outputRoot = root.appendingPathComponent("downloads")
        let fakeCLI = root.appendingPathComponent("fake-melix")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try "mlx-community/Qwen3.5-9B-MLX-4bit\n".write(to: modelList, atomically: true, encoding: .utf8)
        try writeFakeBatchCLI(fakeCLI)

        let runner = MelixCLIRunner(environment: [
            "HOME": root.path,
            "MELIX_CLI": fakeCLI.path,
            "MELIX_HTTP_PORT": "12444",
        ])
        let output = try await runner.run(.batchRun(.init(
            modelListPath: modelList.path,
            runID: "batch-ok",
            outputRoot: outputRoot.path,
            tempRoot: tempRoot.path,
            judgeRemoteServerID: "judge",
            judgeModelID: "gpt-test"
        )))

        #expect(output.contains("Melix batch run complete"))
        #expect(output.contains("[1/1] benchmark succeeded 01"))
        #expect(output.contains("[1/1] semantic judge heartbeat judge/gpt-test"))
        #expect(output.contains("[1/1] evaluation succeeded 01"))
        #expect(output.contains("status=succeeded"))

        let summary = try #require(try parseJSONFile(outputRoot.appendingPathComponent("run-summary.json").path))
        #expect(summary["schema_version"] as? String == "melix.batch.run_summary.v1")
        #expect(summary["status"] as? String == "succeeded")
        #expect(summary["succeeded_models"] as? Int == 1)
        #expect(FileManager.default.fileExists(atPath: outputRoot.appendingPathComponent("RUN_SUMMARY.md").path))
        #expect(FileManager.default.fileExists(atPath: outputRoot.appendingPathComponent("run-summary.csv").path))
        #expect(FileManager.default.fileExists(atPath: outputRoot.appendingPathComponent("index.html").path))

        let manifestLines = try String(contentsOf: tempRoot.appendingPathComponent("manifest.jsonl"), encoding: .utf8)
            .split(separator: "\n")
        let entry = try #require(parseJSONObject(String(manifestLines[0])))
        #expect(entry["status"] as? String == "succeeded")
        #expect(entry["benchmark_job_id"] as? String == "bench-01")
        #expect(entry["evaluation_job_id"] as? String == "eval-01")
        #expect((entry["metric_fields"] as? [String: Any])?["bench.smoke.tokens_per_second"] as? Double == 12.5)
        let steps = try #require(entry["steps"] as? [String: Any])
        let benchmark = try #require(steps["benchmark"] as? [String: Any])
        #expect(benchmark["status"] as? String == "succeeded")
        let exports = try #require(steps["exports"] as? [String: Any])
        #expect(exports["status"] as? String == "succeeded")
        #expect(FileManager.default.fileExists(atPath: entry["benchmark_csv_path"] as? String ?? ""))
        #expect(FileManager.default.fileExists(atPath: entry["evaluation_summary_csv_path"] as? String ?? ""))

        let statusText = try await runner.run(.batchStatus(.init(tempRoot: tempRoot.path)))
        #expect(statusText.contains("Melix batch status"))
        #expect(statusText.contains("[01] succeeded mlx-community/Qwen3.5-9B-MLX-4bit"))
        let statusJSON = try parseJSONObject(try await runner.run(.batchStatus(.init(tempRoot: tempRoot.path, json: true))))
        #expect(statusJSON?["status"] as? String == "succeeded")
    }

    @Test("batch run isolates duplicate explicit model rows by source line")
    func batchRunIsolatesDuplicateExplicitModelRowsBySourceLine() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let modelList = root.appendingPathComponent("models.txt")
        let tempRoot = root.appendingPathComponent("tmp-run")
        let outputRoot = root.appendingPathComponent("downloads")
        let fakeCLI = root.appendingPathComponent("fake-melix")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try """
        A|mlx-community/Duplicate-4bit
        A|mlx-community/Duplicate-4bit
        """.write(to: modelList, atomically: true, encoding: .utf8)
        try writeFakeBatchCLI(fakeCLI)

        let runner = MelixCLIRunner(environment: [
            "HOME": root.path,
            "MELIX_CLI": fakeCLI.path,
            "MELIX_HTTP_PORT": "12444",
        ])
        let output = try await runner.run(.batchRun(.init(
            modelListPath: modelList.path,
            runID: "batch-duplicates",
            outputRoot: outputRoot.path,
            tempRoot: tempRoot.path,
            judgeRemoteServerID: "judge",
            judgeModelID: "gpt-test"
        )))

        #expect(output.contains("[1/2] DONE A status=succeeded"))
        #expect(output.contains("[2/2] DONE A status=succeeded"))
        let manifestLines = try String(contentsOf: tempRoot.appendingPathComponent("manifest.jsonl"), encoding: .utf8)
            .split(separator: "\n")
        #expect(manifestLines.count == 2)
        let entries = try manifestLines.map { try #require(parseJSONObject(String($0))) }
        #expect(entries.map { $0["source_line"] as? Int } == [1, 2])
        #expect(entries.allSatisfy { $0["status"] as? String == "succeeded" })
        let modelDirs = entries.compactMap { $0["model_dir"] as? String }
        #expect(Set(modelDirs).count == 2)
        #expect(modelDirs.allSatisfy { $0.contains("-line-") })
        #expect(modelDirs.allSatisfy { FileManager.default.fileExists(atPath: $0) })
        let commandDirs = modelDirs.map { URL(fileURLWithPath: $0).appendingPathComponent("commands", isDirectory: true) }
        #expect(commandDirs.allSatisfy { FileManager.default.fileExists(atPath: $0.appendingPathComponent("benchmark-1.json").path) })

        let summary = try #require(try parseJSONFile(outputRoot.appendingPathComponent("run-summary.json").path))
        #expect(summary["succeeded_models"] as? Int == 2)
    }

    @Test("batch run treats successful stderr as captured evidence")
    func batchRunTreatsSuccessfulStderrAsCapturedEvidence() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let modelList = root.appendingPathComponent("models.txt")
        let tempRoot = root.appendingPathComponent("tmp-run")
        let outputRoot = root.appendingPathComponent("downloads")
        let fakeCLI = root.appendingPathComponent("fake-melix")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try "mlx-community/Qwen3.5-9B-MLX-4bit\n".write(to: modelList, atomically: true, encoding: .utf8)
        try writeFakeBatchCLI(fakeCLI, warnBench: true)

        let runner = MelixCLIRunner(environment: [
            "HOME": root.path,
            "MELIX_CLI": fakeCLI.path,
            "MELIX_HTTP_PORT": "12444",
        ])
        _ = try await runner.run(.batchRun(.init(
            modelListPath: modelList.path,
            runID: "batch-stderr-warning",
            outputRoot: outputRoot.path,
            tempRoot: tempRoot.path,
            judgeRemoteServerID: "judge",
            judgeModelID: "gpt-test"
        )))

        let manifestLine = try #require(try String(contentsOf: tempRoot.appendingPathComponent("manifest.jsonl"), encoding: .utf8).split(separator: "\n").first)
        let entry = try #require(parseJSONObject(String(manifestLine)))
        #expect(entry["status"] as? String == "succeeded")
        let steps = try #require(entry["steps"] as? [String: Any])
        let benchmark = try #require(steps["benchmark"] as? [String: Any])
        #expect(benchmark["status"] as? String == "succeeded")
        #expect((benchmark["message"] as? String)?.contains("stderr captured") == true)
        let receiptPath = try #require(benchmark["artifact_path"] as? String)
        let receipt = try #require(try parseJSONFile(receiptPath))
        #expect(receipt["exit_code"] as? Int == 0)
        let stderrPath = try #require(benchmark["stderr_path"] as? String)
        let stderr = try String(contentsOfFile: stderrPath, encoding: .utf8)
        #expect(stderr.contains("bench warning"))
    }

    @Test("batch run records partial success and failure attribution")
    func batchRunRecordsPartialSuccessAndFailureAttribution() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let modelList = root.appendingPathComponent("models.txt")
        let tempRoot = root.appendingPathComponent("tmp-run")
        let outputRoot = root.appendingPathComponent("downloads")
        let fakeCLI = root.appendingPathComponent("fake-melix")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try "mlx-community/Qwen3.5-9B-MLX-4bit\n".write(to: modelList, atomically: true, encoding: .utf8)
        try writeFakeBatchCLI(fakeCLI, failEval: true)

        let runner = MelixCLIRunner(environment: [
            "HOME": root.path,
            "MELIX_CLI": fakeCLI.path,
            "MELIX_HTTP_PORT": "12444",
        ])
        let output = try await runner.run(.batchRun(.init(
            modelListPath: modelList.path,
            runID: "batch-partial",
            outputRoot: outputRoot.path,
            tempRoot: tempRoot.path,
            judgeRemoteServerID: "judge",
            judgeModelID: "gpt-test",
            continueOnFailure: true
        )))

        #expect(output.contains("status=partial_success"))
        let summary = try #require(try parseJSONFile(outputRoot.appendingPathComponent("run-summary.json").path))
        #expect(summary["status"] as? String == "partial_success")
        #expect(summary["partial_success_models"] as? Int == 1)
        let manifestLine = try #require(try String(contentsOf: tempRoot.appendingPathComponent("manifest.jsonl"), encoding: .utf8).split(separator: "\n").first)
        let entry = try #require(parseJSONObject(String(manifestLine)))
        #expect(entry["status"] as? String == "partial_success")
        #expect(entry["failure_category"] as? String == "judge_failure")
        #expect(entry["recoverability"] as? String == "operator_action_required")
    }

    @Test("batch resume eval-only reruns missing evaluation")
    func batchResumeEvalOnlyRerunsMissingEvaluation() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let modelList = root.appendingPathComponent("models.txt")
        let tempRoot = root.appendingPathComponent("tmp-run")
        let outputRoot = root.appendingPathComponent("downloads")
        let fakeCLI = root.appendingPathComponent("fake-melix")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try """
        # resume keeps this source line stable
        mlx-community/Qwen3.5-9B-MLX-4bit
        """.write(to: modelList, atomically: true, encoding: .utf8)
        try writeFakeBatchCLI(fakeCLI, failEval: true)

        let failingRunner = MelixCLIRunner(environment: [
            "HOME": root.path,
            "MELIX_CLI": fakeCLI.path,
            "MELIX_HTTP_PORT": "12444",
        ])
        _ = try await failingRunner.run(.batchRun(.init(
            modelListPath: modelList.path,
            runID: "batch-resume",
            outputRoot: outputRoot.path,
            tempRoot: tempRoot.path,
            judgeRemoteServerID: "judge",
            judgeModelID: "gpt-test",
            continueOnFailure: true
        )))

        try writeFakeBatchCLI(fakeCLI, failEval: false)
        let resumeRunner = MelixCLIRunner(environment: [
            "HOME": root.path,
            "MELIX_CLI": fakeCLI.path,
            "MELIX_HTTP_PORT": "12444",
        ])
        let dryRun = try await resumeRunner.run(.batchResume(.init(
            tempRoot: tempRoot.path,
            evalOnly: true,
            dryRun: true
        )))
        #expect(dryRun.contains("Melix batch resume dry-run"))
        #expect(dryRun.contains("RESUME 01 mlx-community/Qwen3.5-9B-MLX-4bit"))

        let output = try await resumeRunner.run(.batchResume(.init(
            tempRoot: tempRoot.path,
            evalOnly: true
        )))
        #expect(output.contains("resume eval-only 01"))
        #expect(output.contains("status=succeeded"))
        let summary = try #require(try parseJSONFile(outputRoot.appendingPathComponent("run-summary.json").path))
        #expect(summary["status"] as? String == "succeeded")
        let manifestLine = try #require(try String(contentsOf: tempRoot.appendingPathComponent("manifest.jsonl"), encoding: .utf8).split(separator: "\n").first)
        let entry = try #require(parseJSONObject(String(manifestLine)))
        #expect(entry["status"] as? String == "succeeded")
        #expect(entry["source_line"] as? Int == 2)
        #expect(entry["evaluation_job_id"] as? String == "eval-01")
        let recoveredModelList = try String(contentsOf: tempRoot.appendingPathComponent("resume-models.txt"), encoding: .utf8)
        #expect(recoveredModelList.split(separator: "\n", omittingEmptySubsequences: false).first?.isEmpty == true)
    }

    @Test("json metric patching preserves user artifact strings that look like the old sentinel")
    func jsonMetricPatchingPreservesUserArtifactStringsThatLookLikeTheOldSentinel() throws {
        let sentinel = "9.9999999999989997e+99"
        let output = try MelixCLIJSONEnvelope.outputEnvelopeString(
            commandID: "doctor",
            traceID: "trace-sentinel",
            result: ["health_status": "healthy"],
            artifacts: [["path": sentinel]]
        )
        let envelope = try #require(parseJSONObject(output))
        let artifacts = try #require(envelope["artifacts"] as? [[String: Any]])
        let metrics = try #require(envelope["metrics"] as? [String: Any])

        #expect(artifacts.first?["path"] as? String == sentinel)
        #expect((metrics["melix.cli.json_encode_ms"] as? Double) != nil)
        #expect(metrics["melix.cli.json_encode_ms"] as? Double != 9.999999999999e99)
    }

    @Test("pipeline dry run writes planned step receipts and a summary")
    func pipelineDryRunWritesPlannedStepReceiptsAndASummary() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("phase8.pipeline.json")
        let receiptURL = root.appendingPathComponent("receipts")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "fake-phase8",
          "inputs": {
            "model_id": "melix-dev-text",
            "model_path": "/tmp/melix-dev-text"
          },
          "steps": [
            {
              "id": "materialize",
              "command": "model.import",
              "args": {
                "path": "${inputs.model_path}",
                "model_id": "${inputs.model_id}",
                "model_kind": "text"
              }
            },
            {
              "id": "rescan_registry",
              "command": "model.roots.rescan",
              "args": {}
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        let output = try await MelixCLIRunner(
            client: StubControlPlaneXPCClient(),
            environment: ["MELIX_HOME": root.path]
        ).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-pipeline-dry-run",
                    dryRun: true
                )
            )
        )
        let summary = try #require(parseJSONObject(output))
        let steps = try #require(summary["steps"] as? [[String: Any]])
        let metrics = try #require(summary["metrics"] as? [String: Any])

        #expect(summary["schema_version"] as? String == "melix.pipeline.run.v1")
        #expect(summary["name"] as? String == "fake-phase8")
        #expect(summary["trace_id"] as? String == "trace-pipeline-dry-run")
        #expect(summary["status"] as? String == "planned")
        #expect(steps.count == 2)
        #expect(steps.allSatisfy { $0["status"] as? String == "planned" })
        #expect((metrics["melix.pipeline.total_ms"] as? Double) != nil)
        #expect(metrics["melix.pipeline.resume_skipped_count"] as? Int == 0)
        #expect(metrics["melix.pipeline.failed_step_count"] as? Int == 0)

        for step in steps {
            let receiptPath = try #require(step["receipt_path"] as? String)
            #expect(FileManager.default.fileExists(atPath: receiptPath))
            let receipt = try #require(try parseJSONFile(receiptPath))
            #expect(receipt["schema_version"] as? String == "melix.cli.output.v1")
            #expect(receipt["status"] as? String == "planned")
        }

        let summaryPath = try #require(summary["summary_path"] as? String)
        #expect(FileManager.default.fileExists(atPath: summaryPath))
    }

    @Test("pipeline dry run covers default receipt roots inputs and command builder variants")
    func pipelineDryRunCoversDefaultReceiptRootsInputsAndCommandBuilderVariants() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("builder-coverage.pipeline.json")
        let inputsURL = root.appendingPathComponent("builder-coverage.inputs.json")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "builder coverage",
          "inputs": {
            "model_id": "melix-dev-text",
            "hub": {
              "repo_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
            },
            "metadata": {
              "suite": "smoke"
            },
            "numeric_value": 7,
            "enabled": true
          },
          "steps": [
            {
              "id": "download",
              "command": "model.hub.download",
              "args": {
                "repo_id": "${inputs.hub.repo_id}",
                "revision": true
              }
            },
            {
              "id": "rescan",
              "command": "model.roots.rescan"
            },
            {
              "id": "update_session",
              "command": "server.session.update",
              "args": {
                "server_session_id": "server-session-1",
                "title": 123,
                "default_model_id": "${inputs.model_id}",
                "served_model_ids": ["${inputs.model_id}"],
                "host": true,
                "port": "8080",
                "rate_limit_per_minute": 60,
                "timeout_seconds": 30
              }
            },
            {
              "id": "select_session",
              "command": "server.session.select"
            },
            {
              "id": "start_server",
              "command": "server.start"
            },
            {
              "id": "chat",
              "command": "chat.run",
              "args": {
                "model_id": "${inputs.model_id}",
                "message": "number ${inputs.numeric_value} flag ${inputs.enabled} object ${inputs.metadata}"
              }
            },
            {
              "id": "train",
              "command": "lora.train",
              "args": {
                "model_id": "${inputs.model_id}",
                "hf_dataset_path": "org/dataset",
                "adapter_name": "adapter",
                "target_repo": "melix/adapter",
                "training_mode": "qlora",
                "rank": 8,
                "response_only": true
              }
            },
            {
              "id": "align",
              "command": "alignment.train",
              "args": {
                "model_id": "${inputs.model_id}",
                "dataset_uri": "/tmp/preference-pairs.jsonl",
                "adapter_name": "aligned-adapter",
                "target_repo": "melix/aligned-adapter",
                "algorithm": "grpo",
                "grpo_candidate_count": 4,
                "reference_model_path": "/tmp/reference-model",
                "reward_model_manifest_path": "/tmp/reward-model.json",
                "kl_penalty": "0.05",
                "max_steps": 2
              }
            },
            {
              "id": "publish_adapter",
              "command": "lora.publish",
              "args": {
                "model_id": "${inputs.model_id}",
                "target_repo": "melix/adapters/demo",
                "adapter_path": "/tmp/adapter.json"
              }
            },
            {
              "id": "publish_merged_path",
              "command": "lora.publish",
              "args": {
                "model_id": "${inputs.model_id}",
                "target_repo": "melix/models/demo-merged",
                "merged_model_path": "/tmp/merged-model",
                "export_kind": "merged"
              }
            },
            {
              "id": "publish_manifest",
              "command": "lora.publish",
              "args": {
                "model_id": "${inputs.model_id}",
                "target_repo": "melix/models/demo-manifest",
                "manifest_path": "/tmp/merged-manifest.json"
              }
            },
            {
              "id": "publish_artifact",
              "command": "lora.publish",
              "args": {
                "model_id": "${inputs.model_id}",
                "target_repo": "melix/adapters/artifact",
                "artifact_path": "/tmp/artifact-adapter.json",
                "artifact_manifest_path": "/tmp/artifact-adapter.json",
                "export_kind": "adapter"
              }
            },
            {
              "id": "convert",
              "command": "convert",
              "args": {
                "model_id": "${inputs.model_id}",
                "output_dir": "/tmp/converted",
                "target_format": "melix_model_bundle"
              }
            },
            {
              "id": "quantize",
              "command": "quantize",
              "args": {
                "model_id": "${inputs.model_id}",
                "output_dir": "/tmp/quantized",
                "quant_profile_id": "q4",
                "weight_quant": "q4",
                "kv_quant": "q8",
                "quantization_mode": "ptq",
                "source_artifact_kind": "merged_adapter",
                "source_artifact_path": "/tmp/merged-model",
                "quantization_backend": " MLX_LM_CONVERT ",
                "mlx_lm_q_bits": " 4 ",
                "mlx_lm_q_group_size": " 128 ",
                "mlx_lm_q_mode": " Affine ",
                "calibration_dataset_uri": "/tmp/calibration.jsonl",
                "quality_delta": "-0.01",
                "latency_delta": "-0.15",
                "local_inference_smoke_mode": " Runtime_Generate ",
                "local_inference_smoke_prompt": "Reply with ISSUE365_OK"
              }
            },
            {
              "id": "upload",
              "command": "upload",
              "args": {
                "model_id": "${inputs.model_id}",
                "output_dir": "/tmp/upload",
                "target_repo": "melix/models/uploaded",
                "artifact_path": "/tmp/quantized",
                "artifact_kind": "quantized_model_bundle",
                "artifact_manifest_path": "/tmp/quantized/manifest.json"
              }
            },
            {
              "id": "activate",
              "command": "lora.activate",
              "args": {
                "model_id": "${inputs.model_id}",
                "adapter_path": "/tmp/adapter.json",
                "alias": "derived-model",
                "activation_mode": "adapter_backed_runtime"
              }
            },
            {
              "id": "bench",
              "command": "bench.run",
              "args": {
                "repo_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                "suite": "smoke,latency",
                "context_length": "1024,2048",
                "generation_length": "128",
                "batch_size": [1, "2"],
                "repeats": 2,
                "cache_profile": "cold",
                "reasoning_mode": "disabled",
                "structured_output_mode": "disabled",
                "sample_size": 4,
                "batch_factor": 2
              }
            },
            {
              "id": "matrix",
              "command": "bench.matrix.run",
              "args": {
                "model_id": "${inputs.model_id}",
                "task_kind": "text-generation",
                "suites": ["smoke", 7],
                "context_lengths": [1024, "2048"],
                "generation_length": "128,256",
                "batch_sizes": [1],
                "cache_profile": "cold,warm",
                "reasoning_mode": "disabled",
                "structured_output_mode": "disabled",
                "concurrency": "1,2",
                "duration_seconds": 30,
                "allow_large_matrix": 1
              }
            },
            {
              "id": "export_bench",
              "command": "bench.export-csv",
              "args": {
                "job_id": "bench-1",
                "output": "/tmp/bench.csv"
              }
            },
            {
              "id": "export_matrix_summary",
              "command": "bench.matrix.export-summary-csv",
              "args": {
                "job_id": "matrix-1",
                "output": "/tmp/matrix-summary.csv"
              }
            },
            {
              "id": "export_matrix_requests",
              "command": "bench.matrix.export-requests-csv",
              "args": {
                "job_id": "matrix-1",
                "output": "/tmp/matrix-requests.csv"
              }
            },
            {
              "id": "eval_csv",
              "command": "eval.run",
              "args": {
                "model_id": "${inputs.model_id}",
                "suite": "mmlu",
                "dataset_id": "mmlu.dev.v1",
                "sample_size": 4,
                "source_csv": "/tmp/eval.csv",
                "field_system_path": "system",
                "field_input_text_path": "input",
                "field_target_path": "target",
                "field_sample_id_path": "id",
                "profile_type": "final_result",
                "result_kind": "text",
                "extraction_mode": "heuristic_final",
                "scoring_mode": "normalized_exact_match",
                "threshold": "0.75",
                "output_schema_json": "{\"type\":\"string\"}",
                "ignored_paths": "metadata.trace,metadata.debug",
                "few_shot": 2,
                "seed": 11,
                "code_exec_policy": "sandboxed"
              }
            },
            {
              "id": "eval_jsonl",
              "command": "eval.run",
              "args": {
                "repo_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                "source_jsonl": "/tmp/eval.jsonl"
              }
            },
            {
              "id": "eval_hf",
              "command": "eval.run",
              "args": {
                "model_id": "${inputs.model_id}",
                "hf_dataset_path": "org/eval",
                "hf_dataset_name": 123,
                "hf_dataset_revision": false,
                "hf_dataset_split": "test"
              }
            },
            {
              "id": "export_eval_summary",
              "command": "eval.export-summary-csv",
              "args": {
                "job_id": "eval-1",
                "output": "/tmp/eval-summary.csv"
              }
            },
            {
              "id": "export_eval_samples_csv",
              "command": "eval.export-samples-csv",
              "args": {
                "job_id": "eval-1",
                "output": "/tmp/eval-samples.csv"
              }
            },
            {
              "id": "export_eval_samples_jsonl",
              "command": "eval.export-samples-jsonl",
              "args": {
                "job_id": "eval-1",
                "output": "/tmp/eval-samples.jsonl"
              }
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)
        try Data(#"{"model_id":"override-model"}"#.utf8).write(to: inputsURL)

        let output = try await MelixCLIRunner(
            client: StubControlPlaneXPCClient(),
            environment: ["MELIX_HOME": root.path]
        ).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    inputsPath: inputsURL.path,
                    traceID: "trace-default-root",
                    dryRun: true
                )
            )
        )
        let summary = try #require(parseJSONObject(output))
        let steps = try #require(summary["steps"] as? [[String: Any]])
        let expectedReceiptDir = root
            .appendingPathComponent("pipelines")
            .appendingPathComponent("builder-coverage")
            .appendingPathComponent("trace-default-root")
            .path
        let chatStep = try #require(steps.first { $0["id"] as? String == "chat" })
        let chatReceiptPath = try #require(chatStep["receipt_path"] as? String)
        let chatReceipt = try #require(try parseJSONFile(chatReceiptPath))
        let chatResult = try #require(chatReceipt["result"] as? [String: Any])
        let chatArguments = try #require(chatResult["arguments"] as? [String])
        let trainStep = try #require(steps.first { $0["id"] as? String == "train" })
        let trainReceiptPath = try #require(trainStep["receipt_path"] as? String)
        let trainReceipt = try #require(try parseJSONFile(trainReceiptPath))
        let trainResult = try #require(trainReceipt["result"] as? [String: Any])
        let trainArguments = try #require(trainResult["arguments"] as? [String])
        let alignStep = try #require(steps.first { $0["id"] as? String == "align" })
        let alignReceiptPath = try #require(alignStep["receipt_path"] as? String)
        let alignReceipt = try #require(try parseJSONFile(alignReceiptPath))
        let alignResult = try #require(alignReceipt["result"] as? [String: Any])
        let alignArguments = try #require(alignResult["arguments"] as? [String])
        let quantizeStep = try #require(steps.first { $0["id"] as? String == "quantize" })
        let quantizeReceiptPath = try #require(quantizeStep["receipt_path"] as? String)
        let quantizeReceipt = try #require(try parseJSONFile(quantizeReceiptPath))
        let quantizeResult = try #require(quantizeReceipt["result"] as? [String: Any])
        let quantizeArguments = try #require(quantizeResult["arguments"] as? [String])

        #expect(summary["receipt_dir"] as? String == expectedReceiptDir)
        #expect(summary["status"] as? String == "planned")
        #expect(steps.count == 27)
        #expect(steps.allSatisfy { $0["status"] as? String == "planned" })
        #expect(chatArguments.contains("override-model"))
        #expect(chatArguments.contains(#"number 7 flag true object {"suite":"smoke"}"#))
        #expect(trainArguments.contains("--response-only"))
        #expect(Array(alignArguments.prefix(2)) == ["alignment", "train"])
        #expect(alignArguments.contains("--algorithm"))
        #expect(alignArguments.contains("grpo"))
        #expect(quantizeArguments.contains("--source-artifact-kind"))
        #expect(quantizeArguments.contains("merged_adapter"))
        #expect(quantizeArguments.contains("--quantization-backend"))
        #expect(quantizeArguments.contains("mlx_lm_convert"))
        #expect(quantizeArguments.contains("--mlx-lm-q-mode"))
        #expect(quantizeArguments.contains("affine"))
        #expect(quantizeArguments.contains("--mlx-lm-q-bits"))
        #expect(quantizeArguments.contains("4"))
        #expect(quantizeArguments.contains("--mlx-lm-q-group-size"))
        #expect(quantizeArguments.contains("128"))
        #expect(quantizeArguments.contains("--local-inference-smoke-mode"))
        #expect(quantizeArguments.contains("runtime_generate"))
    }

    @Test("pipeline dry run redacts Hugging Face download token arguments")
    func pipelineDryRunRedactsHuggingFaceDownloadTokenArguments() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("hf-token-redaction.pipeline.json")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = """
        {
          "schema_version": "melix.pipeline.v1",
          "name": "hf-token-redaction",
          "inputs": {},
          "steps": [
            {
              "id": "download_private_model",
              "command": "model.hub.download",
              "args": {
                "repo_id": "mlx-community/Private-4bit",
                "revision": "main",
                "hf_token": "hf_secret_token"
              }
            }
          ]
        }
        """
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        let output = try await MelixCLIRunner(
            client: StubControlPlaneXPCClient(),
            environment: ["MELIX_HOME": root.path]
        ).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    traceID: "trace-hf-token-redaction",
                    dryRun: true
                )
            )
        )
        let summary = try #require(parseJSONObject(output))
        let steps = try #require(summary["steps"] as? [[String: Any]])
        let step = try #require(steps.first)
        let receiptPath = try #require(step["receipt_path"] as? String)
        let receipt = try #require(try parseJSONFile(receiptPath))
        let result = try #require(receipt["result"] as? [String: Any])
        let arguments = try #require(result["arguments"] as? [String])

        #expect(arguments.contains("--hf-token"))
        #expect(arguments.contains("<redacted>"))
        #expect(arguments.contains("hf_secret_token") == false)
        #expect(String(data: try JSONSerialization.data(withJSONObject: receipt), encoding: .utf8)?.contains("hf_secret_token") == false)
    }

    @Test("pipeline result output path falls back to artifact path")
    func pipelineResultOutputPathFallsBackToArtifactPath() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("artifact-alias.pipeline.json")
        let receiptURL = root.appendingPathComponent("receipts")
        let adapterManifestPath = root.appendingPathComponent("train_lora.adapter.json").path
        let activationManifestPath = root.appendingPathComponent("activate_adapter.json").path
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "artifact-alias",
          "inputs": {
            "model_id": "melix-dev-text"
          },
          "steps": [
            {
              "id": "train_lora",
              "command": "lora.train",
              "args": {
                "model_id": "${inputs.model_id}",
                "dataset_uri": "/tmp/sft.jsonl",
                "adapter_name": "artifact-alias",
                "training_mode": "lora"
              }
            },
            {
              "id": "activate_lora",
              "command": "lora.activate",
              "args": {
                "model_id": "${inputs.model_id}",
                "adapter_path": "${steps.train_lora.result.output_path}",
                "activation_mode": "adapter_backed_runtime",
                "derived_model_alias": "artifact-alias-derived"
              }
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "",
                manifestJSON: #"""
                {
                  "operation": "train_lora",
                  "job_id": "train-1",
                  "artifact_path": "\#(adapterManifestPath)"
                }
                """#
            ),
            forOperation: "train_lora"
        )
        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: activationManifestPath,
                manifestJSON: #"""
                {
                  "operation": "activate_adapter",
                  "job_id": "activate-1",
                  "output_path": "\#(activationManifestPath)"
                }
                """#
            ),
            forOperation: "activate_adapter"
        )

        let output = try await MelixCLIRunner(
            client: client,
            environment: ["MELIX_HOME": root.path]
        ).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-artifact-alias"
                )
            )
        )
        let summary = try #require(parseJSONObject(output))
        let steps = try #require(summary["steps"] as? [[String: Any]])
        let trainStep = try #require(steps.first { $0["id"] as? String == "train_lora" })
        let trainReceiptPath = try #require(trainStep["receipt_path"] as? String)
        let trainReceipt = try #require(try parseJSONFile(trainReceiptPath))
        let trainResult = try #require(trainReceipt["result"] as? [String: Any])
        let calls = await client.modelOperationCalls.filter { $0.ext["melix.registry_rescan"] != "true" }

        #expect(summary["status"] as? String == "succeeded")
        #expect(trainResult["artifact_path"] as? String == adapterManifestPath)
        #expect(trainResult["output_path"] as? String == adapterManifestPath)
        #expect(calls.count == 2)
        #expect(calls[1].operation == "activate_adapter")
        #expect(calls[1].ext["artifact_path"] == adapterManifestPath)
    }

    @Test("successful fake phase 8 pipeline writes receipts summary and artifact paths")
    func successfulFakePhase8PipelineWritesReceiptsSummaryAndArtifactPaths() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("phase8-success.pipeline.json")
        let receiptURL = root.appendingPathComponent("receipts")
        let artifactRoot = root.appendingPathComponent("artifacts")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "fake-phase8-success",
          "inputs": {
            "model_id": "melix-dev-text",
            "derived_model_alias": "melix-dev-text-derived",
            "model_path": "/tmp/melix-dev-text",
            "server_session_id": "server-session-1",
            "bench_job_id": "bench-1",
            "artifact_dir": "\#(artifactRoot.path)"
          },
          "steps": [
            {
              "id": "materialize",
              "command": "model.import",
              "args": {
                "path": "${inputs.model_path}",
                "model_id": "${inputs.model_id}",
                "model_kind": "text"
              },
              "checks": {
                "required_result_fields": ["model_id", "managed_model_path"]
              }
            },
            {
              "id": "rescan_registry",
              "command": "model.roots.rescan",
              "args": {}
            },
            {
              "id": "update_server_session",
              "command": "server.session.update",
              "args": {
                "server_session_id": "${inputs.server_session_id}",
                "title": "Fake Phase 8",
                "default_model_id": "${inputs.model_id}",
                "served_model_ids": ["${inputs.model_id}"],
                "host": "127.0.0.1",
                "port": 8080
              }
            },
            {
              "id": "start_server",
              "command": "server.start",
              "args": {
                "server_session_id": "${inputs.server_session_id}"
              }
            },
            {
              "id": "base_chat",
              "command": "chat.run",
              "args": {
                "model_id": "${inputs.model_id}",
                "server_session_id": "${inputs.server_session_id}",
                "message": "Reply with BASE_OK only."
              },
              "checks": {
                "required_result_fields": ["assistant_text", "request_id"]
              }
            },
            {
              "id": "train_lora",
              "command": "lora.train",
              "args": {
                "model_id": "${inputs.model_id}",
                "dataset_uri": "/tmp/melix-dataset.jsonl",
                "adapter_name": "fake-phase8",
                "derived_model_alias": "${inputs.derived_model_alias}"
              },
              "checks": {
                "required_result_fields": ["job_id", "output_path"]
              }
            },
            {
              "id": "activate_lora",
              "command": "lora.activate",
              "args": {
                "model_id": "${inputs.model_id}",
                "adapter_path": "${steps.train_lora.result.output_path}",
                "activation_mode": "adapter_backed_runtime",
                "derived_model_alias": "${inputs.derived_model_alias}"
              },
              "checks": {
                "required_result_fields": ["job_id"]
              }
            },
            {
              "id": "derived_chat",
              "command": "chat.run",
              "args": {
                "model_id": "${inputs.derived_model_alias}",
                "server_session_id": "${inputs.server_session_id}",
                "message": "Reply with DERIVED_OK only."
              },
              "checks": {
                "required_result_fields": ["assistant_text", "request_id"]
              }
            },
            {
              "id": "run_benchmark",
              "command": "bench.run",
              "args": {
                "model_id": "${inputs.derived_model_alias}",
                "suites": ["smoke"],
                "context_lengths": [1024],
                "generation_length": 128
              },
              "checks": {
                "required_result_fields": ["report_path", "metrics"]
              }
            },
            {
              "id": "run_benchmark_matrix",
              "command": "bench.matrix.run",
              "args": {
                "model_id": "${inputs.derived_model_alias}",
                "suites": ["smoke"],
                "context_lengths": [1024],
                "generation_lengths": [128],
                "batch_sizes": [1],
                "cache_profiles": ["cold"],
                "reasoning_modes": ["disabled"],
                "structured_output_modes": ["disabled"],
                "concurrency": [1],
                "requests": 4,
                "allow_large_matrix": true
              },
              "checks": {
                "required_result_fields": ["job.job_id"]
              }
            },
            {
              "id": "run_evaluation",
              "command": "eval.run",
              "args": {
                "model_id": "${inputs.derived_model_alias}",
                "suites": ["mmlu"],
                "dataset_id": "mmlu.dev.v1",
                "sample_size": 4
              },
              "checks": {
                "required_result_fields": ["0.job.job_id"]
              }
            },
            {
              "id": "export_benchmark_csv",
              "command": "bench.export-csv",
              "args": {
                "job_id": "${inputs.bench_job_id}",
                "output": "${inputs.artifact_dir}/benchmark.csv"
              },
              "checks": {
                "artifact_path_exists": ["${steps.export_benchmark_csv.result.output_path}"]
              }
            },
            {
              "id": "export_matrix_summary_csv",
              "command": "bench.matrix.export-summary-csv",
              "args": {
                "job_id": "${steps.run_benchmark_matrix.result.job.job_id}",
                "output": "${inputs.artifact_dir}/matrix-summary.csv"
              },
              "checks": {
                "artifact_path_exists": ["${steps.export_matrix_summary_csv.result.output_path}"]
              }
            },
            {
              "id": "export_eval_summary_csv",
              "command": "eval.export-summary-csv",
              "args": {
                "job_id": "${steps.run_evaluation.result.0.job.job_id}",
                "output": "${inputs.artifact_dir}/eval-summary.csv"
              },
              "checks": {
                "artifact_path_exists": ["${steps.export_eval_summary_csv.result.output_path}"]
              }
            },
            {
              "id": "export_eval_samples_jsonl",
              "command": "eval.export-samples-jsonl",
              "args": {
                "job_id": "${steps.run_evaluation.result.0.job.job_id}",
                "output": "${inputs.artifact_dir}/eval-samples.jsonl"
              },
              "checks": {
                "artifact_path_exists": ["${steps.export_eval_samples_jsonl.result.output_path}"]
              }
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(models: [
            makeModelSummary(id: "melix-dev-text", kind: "text"),
            makeModelSummary(id: "melix-dev-text-derived", kind: "text"),
        ]))
        await client.setChatExecution(
            requestID: "chat-phase8",
            modelID: "melix-dev-text",
            events: [
                .tokenDelta("OK"),
                .completed(finishReason: "stop", assistantText: "", reasoningText: ""),
            ]
        )
        await client.setBenchResult(
            .init(
                reportPath: "/tmp/melix/bench/bench-1/report.md",
                reportMarkdown: "# Bench\n",
                metrics: ["bench.smoke.ttft_ms": 24.45]
            )
        )
        await client.setBenchMatrixResult(
            .init(
                job: makeBenchmarkMatrixJobSummary(
                    jobID: "bench-matrix-1",
                    modelID: "melix-dev-text-derived",
                    taskKind: "text-generation",
                    sourceRepo: ""
                ),
                summaryRows: []
            )
        )
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-1",
                suiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                metricName: "eval.mmlu.accuracy",
                metricValue: 0.75
            ),
        ])
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))
        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix/train_lora/fake-phase8.adapter.json",
                manifestJSON: #"""
                {
                  "model_id": "melix-dev-text",
                  "managed_model_path": "/tmp/melix-managed/melix-dev-text",
                  "source_kind": "local_path",
                  "source_locator": "/tmp/melix-dev-text",
                  "job_id": "model-op-job-1",
                  "output_path": "/tmp/melix/train_lora/fake-phase8.adapter.json",
                  "ext": {
                    "melix.source_kind": "local_path",
                    "melix.source_locator": "/tmp/melix-dev-text"
                  }
                }
                """#
            )
        )

        let store = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": root.path])
        )
        try await store.save(
            MelixOperatorSessionState(
                selectedServerSessionID: "server-session-1",
                serverSessions: [
                    .init(
                        id: "server-session-1",
                        title: "Fake Phase 8",
                        defaultModelID: "melix-dev-text",
                        servedModelIDs: ["melix-dev-text"]
                    )
                ]
            )
        )

        let output = try await MelixCLIRunner(
            client: client,
            environment: ["MELIX_HOME": root.path],
            operatorSessionStore: store
        ).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-fake-phase8-success"
                )
            )
        )
        let summary = try #require(parseJSONObject(output))
        let steps = try #require(summary["steps"] as? [[String: Any]])
        let metrics = try #require(summary["metrics"] as? [String: Any])
        let exportStep = try #require(steps.first { $0["id"] as? String == "export_eval_samples_jsonl" })
        let artifactPaths = try #require(exportStep["artifact_paths"] as? [String])

        #expect(summary["status"] as? String == "succeeded")
        #expect(steps.count == 15)
        #expect(steps.allSatisfy { $0["status"] as? String == "succeeded" })
        #expect((metrics["melix.pipeline.step_ms.export_eval_samples_jsonl"] as? Double) != nil)
        #expect(artifactPaths == [artifactRoot.appendingPathComponent("eval-samples.jsonl").path])
        #expect(FileManager.default.fileExists(atPath: artifactRoot.appendingPathComponent("benchmark.csv").path))
        #expect(FileManager.default.fileExists(atPath: artifactRoot.appendingPathComponent("matrix-summary.csv").path))
        #expect(FileManager.default.fileExists(atPath: artifactRoot.appendingPathComponent("eval-summary.csv").path))
        #expect(FileManager.default.fileExists(atPath: artifactRoot.appendingPathComponent("eval-samples.jsonl").path))
    }

    @Test("post training pipeline routes alignment publish quantize and local evidence steps")
    func postTrainingPipelineRoutesAlignmentPublishQuantizeAndLocalEvidenceSteps() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("issue365-post-training.pipeline.json")
        let receiptURL = root.appendingPathComponent("receipts")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "issue365-post-training-chain",
          "inputs": {
            "base_model_id": "melix-dev-text",
            "quantized_model_id": "melix-dev-text-aligned-q4",
            "server_session_id": "server-session-issue365"
          },
          "steps": [
            {
              "id": "train_lora",
              "command": "lora.train",
              "args": {
                "model_id": "${inputs.base_model_id}",
                "dataset_uri": "/tmp/sft.jsonl",
                "adapter_name": "issue365-sft",
                "training_mode": "lora",
                "max_steps": 2
              },
              "checks": {
                "required_result_fields": ["job_id", "output_path"]
              }
            },
            {
              "id": "align_adapter",
              "command": "alignment.train",
              "args": {
                "model_id": "${inputs.base_model_id}",
                "dataset_uri": "/tmp/preference-pairs.jsonl",
                "dataset_source_kind": "local_package",
                "adapter_name": "issue365-dpo",
                "algorithm": " DPO ",
                "reference_model_path": "${steps.train_lora.result.output_path}",
                "candidate_generation_mode": "scored_trace",
                "candidate_scoring_mode": "dataset_score",
                "max_steps": 2
              },
              "checks": {
                "required_result_fields": ["job_id", "output_path", "alignment_run_manifest_path"]
              }
            },
            {
              "id": "publish_merged",
              "command": "lora.publish",
              "args": {
                "model_id": "${inputs.base_model_id}",
                "target_repo": "melix/models/issue365-dpo-merged",
                "adapter_path": "   ",
                "manifest_path": "${steps.align_adapter.result.output_path}",
                "export_kind": " MERGED ",
                "publish_backend": "local_filesystem",
                "local_publish_root": "/tmp/melix/issue365-local-publish"
              },
              "checks": {
                "required_result_fields": ["job_id", "output_path"]
              }
            },
            {
              "id": "quantize_merged",
              "command": "quantize",
              "args": {
                "model_id": "${inputs.base_model_id}",
                "output_dir": "/tmp/melix/quantized/issue365-dpo-q4",
                "quant_profile_id": "q4",
                "weight_quant": "q4",
                "kv_quant": "q8",
                "quantization_mode": " PTQ ",
                "source_artifact_kind": " MERGED_ADAPTER ",
                "source_artifact_path": "${steps.publish_merged.result.output_path}",
                "quantization_backend": " MLX_LM_CONVERT ",
                "mlx_lm_q_mode": " AFFINE ",
                "calibration_dataset_uri": "/tmp/calibration.jsonl",
                "quality_delta": "-0.01",
                "latency_delta": "-0.12",
                "local_inference_smoke_mode": " runtime_generate ",
                "local_inference_smoke_prompt": "Reply with ISSUE365_OK"
              },
              "checks": {
                "required_result_fields": ["job_id", "output_path", "local_inference_smoke.status"],
                "equals": {
                  "result.local_inference_smoke.status": "passed",
                  "result.local_inference_smoke.smoke_mode": "runtime_generate"
                }
              }
            },
            {
              "id": "activate_adapter_runtime",
              "command": "lora.activate",
              "args": {
                "model_id": "${inputs.base_model_id}",
                "adapter_path": "${steps.align_adapter.result.output_path}",
                "activation_mode": "adapter_backed_runtime",
                "derived_model_alias": "${inputs.quantized_model_id}"
              },
              "checks": {
                "required_result_fields": ["job_id", "output_path"]
              }
            },
            {
              "id": "local_chat_smoke",
              "command": "chat.run",
              "args": {
                "model_id": "${inputs.quantized_model_id}",
                "server_session_id": "${inputs.server_session_id}",
                "message": "Reply with ISSUE365_OK only."
              },
              "checks": {
                "required_result_fields": ["assistant_text", "request_id"]
              }
            },
            {
              "id": "eval_smoke",
              "command": "eval.run",
              "args": {
                "model_id": "${inputs.quantized_model_id}",
                "suites": ["smoke"],
                "dataset_id": "issue365.smoke.v1",
                "sample_size": 2
              },
              "checks": {
                "required_result_fields": ["0.job.job_id"]
              }
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(models: [
            makeModelSummary(id: "melix-dev-text", kind: "text"),
            makeModelSummary(id: "melix-dev-text-aligned-q4", kind: "text"),
        ]))
        await client.setChatExecution(
            requestID: "chat-issue365",
            modelID: "melix-dev-text-aligned-q4",
            events: [
                .tokenDelta("ISSUE365_OK"),
                .completed(finishReason: "stop", assistantText: "", reasoningText: ""),
            ]
        )
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-issue365",
                suiteID: "smoke",
                datasetID: "issue365.smoke.v1",
                metricName: "eval.smoke.accuracy",
                metricValue: 1.0
            ),
        ])
        let executor = RecordingCLICommandExecutor(
            responses: [
                #"{"operation":"registry_snapshot","adapters":[]}"#,
                #"{"operation":"train_lora","job_id":"lora-job-1","output_path":"/tmp/melix/train_lora/issue365-sft.adapter.json"}"#,
                #"{"operation":"registry_snapshot","adapters":[]}"#,
                #"{"operation":"train_alignment","job_id":"align-job-1","output_path":"/tmp/melix/alignment/issue365-dpo.adapter.json","alignment_run_manifest_path":"/tmp/melix/alignment/issue365-dpo.alignment_run.json"}"#,
                #"{"operation":"upload","job_id":"publish-job-1","output_path":"/tmp/melix/publish/issue365-dpo-merged","artifact_manifest_path":"/tmp/melix/publish/issue365-dpo-merged/manifest.json"}"#,
                #"{"operation":"registry_snapshot","adapters":[]}"#,
                #"{"operation":"quantize","job_id":"quantize-job-1","output_path":"/tmp/melix/quantized/issue365-dpo-q4","bundle_path":"/tmp/melix/quantized/issue365-dpo-q4","local_inference_smoke":{"status":"passed","smoke_mode":"runtime_generate"}}"#,
                #"{"operation":"registry_snapshot","adapters":[]}"#,
                #"{"operation":"activate_adapter","job_id":"activate-job-1","output_path":"/tmp/melix/activate_adapter/issue365-dpo"}"#,
                #"{"operation":"registry_snapshot","adapters":[]}"#,
                #"{"operation":"registry_snapshot","adapters":[]}"#,
            ]
        )

        let output = try await MelixCLIRunner(
            client: client,
            environment: ["MELIX_HOME": root.path],
            commandExecutor: executor.run
        ).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-issue365-post-training"
                )
            )
        )
        let summary = try #require(parseJSONObject(output))
        let steps = try #require(summary["steps"] as? [[String: Any]])
        let quantizeStep = try #require(steps.first { $0["id"] as? String == "quantize_merged" })
        let quantizeArtifactPaths = try #require(quantizeStep["artifact_paths"] as? [String])
        let commands = await executor.commands
        let operationCommands = commands.filter { Array($0.prefix(2)) != ["lora", "list"] }

        #expect(summary["status"] as? String == "succeeded")
        #expect(steps.count == 7)
        #expect(steps.allSatisfy { $0["status"] as? String == "succeeded" })
        #expect(operationCommands.count == 5)
        #expect(Array(operationCommands[0].prefix(2)) == ["lora", "train"])
        #expect(Array(operationCommands[1].prefix(2)) == ["alignment", "train"])
        #expect(operationCommands[1].contains("--reference-model-path"))
        #expect(operationCommands[1].contains("/tmp/melix/train_lora/issue365-sft.adapter.json"))
        #expect(operationCommands[1].contains("--candidate-generation-mode"))
        #expect(operationCommands[1].contains("scored_trace"))
        #expect(operationCommands[1].contains("--candidate-scoring-mode"))
        #expect(operationCommands[1].contains("dataset_score"))
        #expect(operationCommands[1].contains("--algorithm"))
        #expect(operationCommands[1].contains("dpo"))
        #expect(operationCommands[1].contains(where: { $0.contains("dataset_source_kind") }) == false)
        #expect(Array(operationCommands[2].prefix(2)) == ["lora", "publish"])
        #expect(operationCommands[2].contains("/tmp/melix/alignment/issue365-dpo.adapter.json"))
        #expect(operationCommands[2].contains("--publish-backend"))
        #expect(operationCommands[2].contains("local_filesystem"))
        #expect(operationCommands[2].contains("--local-publish-root"))
        #expect(operationCommands[2].contains("/tmp/melix/issue365-local-publish"))
        #expect(operationCommands[2].contains(where: { $0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) == false)
        #expect(operationCommands[3].starts(with: ["quantize", "--model-id", "melix-dev-text"]))
        #expect(operationCommands[3].contains("--quantization-mode"))
        #expect(operationCommands[3].contains("ptq"))
        #expect(operationCommands[3].contains("--source-artifact-kind"))
        #expect(operationCommands[3].contains("merged_adapter"))
        #expect(operationCommands[3].contains("--source-artifact-path"))
        #expect(operationCommands[3].contains("/tmp/melix/publish/issue365-dpo-merged"))
        #expect(operationCommands[3].contains("--quantization-backend"))
        #expect(operationCommands[3].contains("mlx_lm_convert"))
        #expect(operationCommands[3].contains("--mlx-lm-q-mode"))
        #expect(operationCommands[3].contains("affine"))
        #expect(operationCommands[3].contains("--local-inference-smoke-mode"))
        #expect(operationCommands[3].contains("runtime_generate"))
        #expect(operationCommands[3].contains("--local-inference-smoke-prompt"))
        #expect(operationCommands[3].contains("Reply with ISSUE365_OK"))
        #expect(Array(operationCommands[4].prefix(2)) == ["lora", "activate"])
        #expect(quantizeArtifactPaths.contains("/tmp/melix/quantized/issue365-dpo-q4"))
    }

    @Test("pipeline writes an error receipt and summary when a step fails")
    func pipelineWritesErrorReceiptAndSummaryWhenAStepFails() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("failing.pipeline.json")
        let receiptURL = root.appendingPathComponent("receipts")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "failing-pipeline",
          "inputs": {},
          "steps": [
            {
              "id": "unsupported",
              "command": "unsupported.command",
              "args": {}
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        do {
            _ = try await MelixCLIRunner(client: StubControlPlaneXPCClient()).run(
                .pipelineRun(
                    .init(
                        filePath: pipelineURL.path,
                        receiptDir: receiptURL.path,
                        traceID: "trace-failing-pipeline"
                    )
                )
            )
            Issue.record("Expected unsupported pipeline command to fail.")
        } catch let error as MelixCLIError {
            #expect(error.errorDescription == "Unsupported pipeline command unsupported.command.")
        }

        let summary = try #require(try parseJSONFile(receiptURL.appendingPathComponent("run.json").path))
        let steps = try #require(summary["steps"] as? [[String: Any]])
        let errorReceiptPath = try #require(steps.first?["receipt_path"] as? String)
        let errorReceipt = try #require(try parseJSONFile(errorReceiptPath))
        let receiptError = try #require(errorReceipt["error"] as? [String: Any])

        #expect(summary["status"] as? String == "failed")
        #expect(steps.first?["status"] as? String == "failed")
        #expect(errorReceipt["schema_version"] as? String == "melix.cli.error.v1")
        #expect(receiptError["code"] as? String == "usage")
    }

    @Test("pipeline writes an error receipt and summary when a step throws a non Melix error")
    func pipelineWritesErrorReceiptAndSummaryForNonMelixStepErrors() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("generic-failing.pipeline.json")
        let receiptURL = root.appendingPathComponent("receipts")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "generic-failing-pipeline",
          "inputs": {},
          "steps": [
            {
              "id": "materialize",
              "command": "model.import",
              "args": {
                "path": "/tmp/melix-dev-text",
                "model_id": "melix-dev-text",
                "model_kind": "text"
              }
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        let client = StubControlPlaneXPCClient()
        await client.setModelOperationError(NonMelixPipelineTestError(message: "transport disconnected"))
        do {
            _ = try await MelixCLIRunner(client: client).run(
                .pipelineRun(
                    .init(
                        filePath: pipelineURL.path,
                        receiptDir: receiptURL.path,
                        traceID: "trace-generic-failing-pipeline"
                    )
                )
            )
            Issue.record("Expected generic pipeline step error to fail.")
        } catch {
            #expect(String(describing: error).contains("transport disconnected"))
        }

        let summary = try #require(try parseJSONFile(receiptURL.appendingPathComponent("run.json").path))
        let steps = try #require(summary["steps"] as? [[String: Any]])
        let errorReceiptPath = try #require(steps.first?["receipt_path"] as? String)
        let errorReceipt = try #require(try parseJSONFile(errorReceiptPath))
        let receiptError = try #require(errorReceipt["error"] as? [String: Any])

        #expect(summary["status"] as? String == "failed")
        #expect(steps.first?["status"] as? String == "failed")
        #expect(errorReceipt["schema_version"] as? String == "melix.cli.error.v1")
        #expect(receiptError["code"] as? String == "runtime")
        #expect((receiptError["message"] as? String)?.contains("transport disconnected") == true)
    }

    @Test("pipeline resume skips successful receipts and rejects changed hashes")
    func pipelineResumeSkipsSuccessfulReceiptsAndRejectsChangedHashes() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("resume.pipeline.json")
        let receiptURL = root.appendingPathComponent("receipts")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "resume-pipeline",
          "inputs": {
            "model_id": "melix-dev-text",
            "model_path": "/tmp/melix-dev-text"
          },
          "steps": [
            {
              "id": "materialize",
              "command": "model.import",
              "args": {
                "path": "${inputs.model_path}",
                "model_id": "${inputs.model_id}",
                "model_kind": "text"
              }
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        let firstClient = StubControlPlaneXPCClient()
        await firstClient.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-managed/melix-dev-text",
                manifestJSON: #"""
                {
                  "model_id": "melix-dev-text",
                  "ext": {
                    "melix.source_kind": "local_path",
                    "melix.source_locator": "/tmp/melix-dev-text"
                  }
                }
                """#
            )
        )
        _ = try await MelixCLIRunner(client: firstClient).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-resume-pipeline"
                )
            )
        )

        let resumeClient = StubControlPlaneXPCClient()
        let resumedOutput = try await MelixCLIRunner(client: resumeClient).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-resume-pipeline",
                    resume: true
                )
            )
        )
        let resumedSummary = try #require(parseJSONObject(resumedOutput))
        let resumedMetrics = try #require(resumedSummary["metrics"] as? [String: Any])
        let resumedSteps = try #require(resumedSummary["steps"] as? [[String: Any]])

        #expect(resumedSteps.first?["status"] as? String == "skipped")
        #expect(resumedMetrics["melix.pipeline.resume_skipped_count"] as? Double == 1)
        #expect(await resumeClient.lastModelOperationCall == nil)

        try Data(pipelineJSON.replacingOccurrences(of: "melix-dev-text", with: "melix-dev-text-v2").utf8)
            .write(to: pipelineURL)
        do {
            _ = try await MelixCLIRunner(client: StubControlPlaneXPCClient()).run(
                .pipelineRun(
                    .init(
                        filePath: pipelineURL.path,
                        receiptDir: receiptURL.path,
                        traceID: "trace-resume-pipeline",
                        resume: true
                    )
                )
            )
            Issue.record("Expected resume to reject changed pipeline and input hashes.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("Pipeline resume metadata does not match the current pipeline or inputs."))
        }
    }

    @Test("pipeline from step rejects unknown targets and persists a failed summary")
    func pipelineFromStepRejectsUnknownTargetsAndPersistsAFailedSummary() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("from-step-unknown.pipeline.json")
        let receiptURL = root.appendingPathComponent("receipts")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "from-step-unknown",
          "inputs": {},
          "steps": [
            {
              "id": "rescan_registry",
              "command": "model.roots.rescan",
              "args": {}
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        _ = try await MelixCLIRunner(client: StubControlPlaneXPCClient()).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-from-step-unknown",
                    dryRun: true
                )
            )
        )

        do {
            _ = try await MelixCLIRunner(client: StubControlPlaneXPCClient()).run(
                .pipelineRun(
                    .init(
                        filePath: pipelineURL.path,
                        receiptDir: receiptURL.path,
                        traceID: "trace-from-step-unknown",
                        fromStepID: "missing_step",
                        dryRun: true
                    )
                )
            )
            Issue.record("Expected unknown --from-step to fail.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("--from-step missing_step does not match any pipeline step."))
        }

        let summary = try #require(try parseJSONFile(receiptURL.appendingPathComponent("run.json").path))
        let metrics = try #require(summary["metrics"] as? [String: Any])
        let error = try #require(summary["error"] as? [String: Any])

        #expect(summary["status"] as? String == "failed")
        #expect(error["code"] as? String == "runtime")
        #expect(error["message"] as? String == "--from-step missing_step does not match any pipeline step.")
        #expect(metrics["melix.pipeline.failed_step_count"] as? Double == 1)
        #expect((metrics["melix.pipeline.receipt_write_ms"] as? Double ?? 0) > 0)
    }

    @Test("pipeline from step loads prior receipts and reruns from the requested step")
    func pipelineFromStepLoadsPriorReceiptsAndRerunsFromRequestedStep() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("from-step.pipeline.json")
        let receiptURL = root.appendingPathComponent("receipts")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "from-step",
          "inputs": {
            "model_path": "/tmp/melix-dev-text"
          },
          "steps": [
            {
              "id": "materialize",
              "command": "model.import",
              "args": {
                "path": "${inputs.model_path}",
                "model_id": "melix-dev-text",
                "model_kind": "text"
              }
            },
            {
              "id": "chat",
              "command": "chat.run",
              "args": {
                "model_id": "${steps.materialize.result.model_id}",
                "message": "Say OK."
              }
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        let firstClient = StubControlPlaneXPCClient()
        await firstClient.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-managed/melix-dev-text",
                manifestJSON: #"""
                {
                  "model_id": "melix-dev-text",
                  "managed_model_path": "/tmp/melix-managed/melix-dev-text"
                }
                """#
            )
        )
        await firstClient.setChatExecution(
            requestID: "chat-initial",
            modelID: "melix-dev-text",
            events: [
                .tokenDelta("OK"),
                .completed(finishReason: "stop", assistantText: "", reasoningText: ""),
            ]
        )
        _ = try await MelixCLIRunner(client: firstClient).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-from-step"
                )
            )
        )
        let materializeReceiptURL = receiptURL
            .appendingPathComponent("steps")
            .appendingPathComponent("001-materialize.json")
        let materializeReceiptBefore = try Data(contentsOf: materializeReceiptURL)

        let resumeClient = StubControlPlaneXPCClient()
        await resumeClient.setChatExecution(
            requestID: "chat-rerun",
            modelID: "melix-dev-text",
            events: [
                .tokenDelta("RERUN_OK"),
                .completed(finishReason: "stop", assistantText: "", reasoningText: ""),
            ]
        )
        let output = try await MelixCLIRunner(client: resumeClient).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-from-step",
                    fromStepID: "chat"
                )
            )
        )
        let summary = try #require(parseJSONObject(output))
        let steps = try #require(summary["steps"] as? [[String: Any]])
        let chatRequest = try #require(await resumeClient.lastChatRequest)
        let materializeReceiptAfter = try Data(contentsOf: materializeReceiptURL)

        #expect(steps.map { $0["status"] as? String } == ["loaded", "succeeded"])
        #expect(materializeReceiptAfter == materializeReceiptBefore)
        #expect(chatRequest.modelID == "melix-dev-text")
    }

    @Test("pipeline resume rejects stale step receipts")
    func pipelineResumeRejectsStaleStepReceipts() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("resume-stale.pipeline.json")
        let receiptURL = root.appendingPathComponent("receipts")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "resume-stale",
          "inputs": {
            "model_id": "melix-dev-text",
            "model_path": "/tmp/melix-dev-text"
          },
          "steps": [
            {
              "id": "materialize",
              "command": "model.import",
              "args": {
                "path": "${inputs.model_path}",
                "model_id": "${inputs.model_id}",
                "model_kind": "text"
              }
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        let firstClient = StubControlPlaneXPCClient()
        await firstClient.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-managed/melix-dev-text",
                manifestJSON: #"""
                {
                  "model_id": "melix-dev-text",
                  "managed_model_path": "/tmp/melix-managed/melix-dev-text"
                }
                """#
            )
        )
        _ = try await MelixCLIRunner(client: firstClient).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-resume-stale"
                )
            )
        )

        let receiptPath = receiptURL
            .appendingPathComponent("steps")
            .appendingPathComponent("001-materialize.json")
        var receipt = try #require(try parseJSONFile(receiptPath.path))
        receipt["command_id"] = "chat.run"
        try writeJSONObjectForTest(receipt, to: receiptPath)

        do {
            _ = try await MelixCLIRunner(client: StubControlPlaneXPCClient()).run(
                .pipelineRun(
                    .init(
                        filePath: pipelineURL.path,
                        receiptDir: receiptURL.path,
                        traceID: "trace-resume-stale",
                        resume: true
                    )
                )
            )
            Issue.record("Expected resume to reject a stale step receipt.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("Pipeline receipt for step materialize does not match the current command model.import."))
        }
    }

    @Test("pipeline rejects invalid schema and argument value types")
    func pipelineRejectsInvalidSchemaAndArgumentValueTypes() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let cases: [(name: String, json: String, expected: String)] = [
            (
                "inputs-array",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "invalid-inputs",
                  "inputs": [],
                  "steps": [
                    {"id": "rescan", "command": "model.roots.rescan", "args": {}}
                  ]
                }
                """#,
                "Pipeline inputs must be a JSON object."
            ),
            (
                "args-array",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "invalid-args",
                  "inputs": {},
                  "steps": [
                    {"id": "rescan", "command": "model.roots.rescan", "args": []}
                  ]
                }
                """#,
                "Pipeline step rescan args must be a JSON object."
            ),
            (
                "when-array",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "invalid-when",
                  "inputs": {},
                  "steps": [
                    {"id": "rescan", "command": "model.roots.rescan", "args": {}, "when": []}
                  ]
                }
                """#,
                "Pipeline step rescan when must be a JSON object."
            ),
            (
                "checks-array",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "invalid-checks",
                  "inputs": {},
                  "steps": [
                    {"id": "rescan", "command": "model.roots.rescan", "args": {}, "checks": []}
                  ]
                }
                """#,
                "Pipeline step rescan checks must be a JSON object."
            ),
            (
                "invalid-bool",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "invalid-bool",
                  "inputs": {},
                  "steps": [
                    {
                      "id": "matrix",
                      "command": "bench.matrix.run",
                      "args": {
                        "allow_large_matrix": "maybe"
                      }
                    }
                  ]
                }
                """#,
                "Pipeline command argument allow_large_matrix must be a boolean."
            ),
            (
                "invalid-uint-array",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "invalid-uint-array",
                  "inputs": {},
                  "steps": [
                    {
                      "id": "bench",
                      "command": "bench.run",
                      "args": {
                        "context_lengths": ["not-a-number"]
                      }
                    }
                  ]
                }
                """#,
                "Pipeline command argument context_lengths must be an array of unsigned integers."
            ),
            (
                "alignment-missing-algorithm",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "alignment-missing-algorithm",
                  "inputs": {},
                  "steps": [
                    {
                      "id": "align",
                      "command": "alignment.train",
                      "args": {
                        "model_id": "melix-dev-text",
                        "dataset_uri": "/tmp/preference-pairs.jsonl",
                        "adapter_name": "aligned-adapter"
                      }
                    }
                  ]
                }
                """#,
                "Pipeline command argument algorithm is required."
            ),
            (
                "alignment-invalid-algorithm",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "alignment-invalid-algorithm",
                  "inputs": {},
                  "steps": [
                    {
                      "id": "align",
                      "command": "alignment.train",
                      "args": {
                        "model_id": "melix-dev-text",
                        "dataset_uri": "/tmp/preference-pairs.jsonl",
                        "adapter_name": "aligned-adapter",
                        "algorithm": "ppo"
                      }
                    }
                  ]
                }
                """#,
                "Pipeline command argument algorithm must be one of: dpo, orpo, cpo, grpo, rlhf."
            ),
            (
                "quantize-invalid-mode",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "quantize-invalid-mode",
                  "inputs": {},
                  "steps": [
                    {
                      "id": "quantize",
                      "command": "quantize",
                      "args": {
                        "model_id": "melix-dev-text",
                        "quantization_mode": "dynamic"
                      }
                    }
                  ]
                }
                """#,
                "Pipeline command argument quantization_mode must be one of: ptq, qat."
            ),
            (
                "quantize-invalid-source-kind",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "quantize-invalid-source-kind",
                  "inputs": {},
                  "steps": [
                    {
                      "id": "quantize",
                      "command": "quantize",
                      "args": {
                        "model_id": "melix-dev-text",
                        "source_artifact_kind": "checkpoint"
                      }
                    }
                  ]
                }
                """#,
                "Pipeline command argument source_artifact_kind must be one of: base_model, merged_adapter, adapter_export."
            ),
            (
                "quantize-invalid-backend",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "quantize-invalid-backend",
                  "inputs": {},
                  "steps": [
                    {
                      "id": "quantize",
                      "command": "quantize",
                      "args": {
                        "model_id": "melix-dev-text",
                        "quantization_backend": "script"
                      }
                    }
                  ]
                }
                """#,
                "Pipeline command argument quantization_backend must be one of: manifest_only, mlx_lm_convert."
            ),
            (
                "quantize-invalid-mlx-q-mode",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "quantize-invalid-mlx-q-mode",
                  "inputs": {},
                  "steps": [
                    {
                      "id": "quantize",
                      "command": "quantize",
                      "args": {
                        "model_id": "melix-dev-text",
                        "mlx_lm_q_mode": "log"
                      }
                    }
                  ]
                }
                """#,
                "Pipeline command argument mlx_lm_q_mode must be one of: affine, mxfp4, nvfp4, mxfp8."
            ),
            (
                "quantize-invalid-mlx-q-bits",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "quantize-invalid-mlx-q-bits",
                  "inputs": {},
                  "steps": [
                    {
                      "id": "quantize",
                      "command": "quantize",
                      "args": {
                        "model_id": "melix-dev-text",
                        "mlx_lm_q_bits": "four"
                      }
                    }
                  ]
                }
                """#,
                "Pipeline command argument mlx_lm_q_bits must be an integer."
            ),
            (
                "quantize-invalid-mlx-q-group-size",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "quantize-invalid-mlx-q-group-size",
                  "inputs": {},
                  "steps": [
                    {
                      "id": "quantize",
                      "command": "quantize",
                      "args": {
                        "model_id": "melix-dev-text",
                        "mlx_lm_q_group_size": "wide"
                      }
                    }
                  ]
                }
                """#,
                "Pipeline command argument mlx_lm_q_group_size must be an integer."
            ),
            (
                "quantize-invalid-smoke-mode",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "quantize-invalid-smoke-mode",
                  "inputs": {},
                  "steps": [
                    {
                      "id": "quantize",
                      "command": "quantize",
                      "args": {
                        "model_id": "melix-dev-text",
                        "local_inference_smoke_mode": "screenshot"
                      }
                    }
                  ]
                }
                """#,
                "Pipeline command argument local_inference_smoke_mode must be one of: structural, runtime_generate."
            ),
            (
                "publish-missing-artifact-selector",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "publish-missing-artifact-selector",
                  "inputs": {},
                  "steps": [
                    {
                      "id": "publish",
                      "command": "lora.publish",
                      "args": {
                        "model_id": "melix-dev-text",
                        "target_repo": "melix/adapters/demo"
                      }
                    }
                  ]
                }
                """#,
                "Exactly one of adapter_path, merged_model_path, manifest_path, or artifact_path is required for pipeline command lora.publish."
            ),
            (
                "publish-adapter-kind-mismatch",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "publish-adapter-kind-mismatch",
                  "inputs": {},
                  "steps": [
                    {
                      "id": "publish",
                      "command": "lora.publish",
                      "args": {
                        "model_id": "melix-dev-text",
                        "target_repo": "melix/adapters/demo",
                        "adapter_path": "/tmp/adapter.json",
                        "export_kind": "merged"
                      }
                    }
                  ]
                }
                """#,
                "Pipeline command argument export_kind merged is incompatible with adapter_path."
            ),
            (
                "publish-merged-kind-mismatch",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "publish-merged-kind-mismatch",
                  "inputs": {},
                  "steps": [
                    {
                      "id": "publish",
                      "command": "lora.publish",
                      "args": {
                        "model_id": "melix-dev-text",
                        "target_repo": "melix/models/demo",
                        "merged_model_path": "/tmp/merged-model",
                        "export_kind": "adapter"
                      }
                    }
                  ]
                }
                """#,
                "Pipeline command argument export_kind adapter is incompatible with merged_model_path."
            ),
            (
                "publish-artifact-missing-export-kind",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "publish-artifact-missing-export-kind",
                  "inputs": {},
                  "steps": [
                    {
                      "id": "publish",
                      "command": "lora.publish",
                      "args": {
                        "model_id": "melix-dev-text",
                        "target_repo": "melix/adapters/demo",
                        "artifact_path": "/tmp/artifact.json"
                      }
                    }
                  ]
                }
                """#,
                "Pipeline command argument export_kind is required when lora.publish uses artifact_path."
            ),
            (
                "publish-invalid-export-kind",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "publish-invalid-export-kind",
                  "inputs": {},
                  "steps": [
                    {
                      "id": "publish",
                      "command": "lora.publish",
                      "args": {
                        "model_id": "melix-dev-text",
                        "target_repo": "melix/adapters/demo",
                        "adapter_path": "/tmp/adapter.json",
                        "export_kind": "full"
                      }
                    }
                  ]
                }
                """#,
                "Pipeline command argument export_kind must be one of: adapter, merged."
            ),
        ]

        for item in cases {
            let pipelineURL = root.appendingPathComponent("\(item.name).pipeline.json")
            let receiptURL = root.appendingPathComponent("\(item.name)-receipts")
            try Data(item.json.utf8).write(to: pipelineURL)

            do {
                _ = try await MelixCLIRunner(client: StubControlPlaneXPCClient()).run(
                    .pipelineRun(
                        .init(
                            filePath: pipelineURL.path,
                            receiptDir: receiptURL.path,
                            traceID: "trace-\(item.name)",
                            dryRun: true
                        )
                    )
                )
                Issue.record("Expected invalid pipeline case \(item.name) to fail.")
            } catch let error as MelixCLIError {
                #expect(error.localizedDescription == item.expected)
            }
        }
    }

    @Test("pipeline validates skipped commands without resolving skipped arguments")
    func pipelineValidatesSkippedCommandsWithoutResolvingSkippedArguments() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let validSkippedPipelineURL = root.appendingPathComponent("valid-skipped.pipeline.json")
        try Data(
            #"""
            {
              "schema_version": "melix.pipeline.v1",
              "name": "valid-skipped",
              "inputs": {
                "mode": "local"
              },
              "steps": [
                {
                  "id": "download",
                  "command": "model.hub.download",
                  "when": {
                    "input": "mode",
                    "equals": "hub"
                  },
                  "args": {
                    "repo_id": "${inputs.repo_id}"
                  }
                }
              ]
            }
            """#.utf8
        )
        .write(to: validSkippedPipelineURL)

        let summaryText = try await MelixCLIRunner(client: StubControlPlaneXPCClient()).run(
            .pipelineRun(
                .init(
                    filePath: validSkippedPipelineURL.path,
                    receiptDir: root.appendingPathComponent("valid-skipped-receipts").path,
                    traceID: "trace-valid-skipped",
                    dryRun: true
                )
            )
        )
        let summary = try #require(parseJSONObject(summaryText))
        let steps = try #require(summary["steps"] as? [[String: Any]])
        #expect(steps.first?["status"] as? String == "skipped")

        let invalidSkippedPipelineURL = root.appendingPathComponent("invalid-skipped.pipeline.json")
        try Data(
            #"""
            {
              "schema_version": "melix.pipeline.v1",
              "name": "invalid-skipped",
              "inputs": {
                "mode": "local"
              },
              "steps": [
                {
                  "id": "unsupported",
                  "command": "unsupported.command",
                  "when": {
                    "input": "mode",
                    "equals": "hub"
                  },
                  "args": {
                    "ignored": "${inputs.missing}"
                  }
                }
              ]
            }
            """#.utf8
        )
        .write(to: invalidSkippedPipelineURL)

        do {
            _ = try await MelixCLIRunner(client: StubControlPlaneXPCClient()).run(
                .pipelineRun(
                    .init(
                        filePath: invalidSkippedPipelineURL.path,
                        receiptDir: root.appendingPathComponent("invalid-skipped-receipts").path,
                        traceID: "trace-invalid-skipped",
                        dryRun: true
                    )
                )
            )
            Issue.record("Expected skipped unsupported commands to be rejected.")
        } catch let error as MelixCLIError {
            #expect(error == .usage("Unsupported pipeline command unsupported.command."))
        }
    }

    @Test("pipeline when equality compares nested JSON values structurally")
    func pipelineWhenEqualityComparesNestedJSONValuesStructurally() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("nested-when.pipeline.json")
        let receiptURL = root.appendingPathComponent("nested-when-receipts")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "nested-when",
          "inputs": {
            "gate": {
              "enabled": true,
              "labels": ["base", "derived"],
              "profile": {
                "name": "acceptance",
                "limits": [1, 2, 3]
              }
            }
          },
          "steps": [
            {
              "id": "rescan",
              "command": "model.roots.rescan",
              "when": {
                "input": "gate",
                "equals": {
                  "profile": {
                    "limits": [1, 2, 3],
                    "name": "acceptance"
                  },
                  "labels": ["base", "derived"],
                  "enabled": true
                }
              },
              "args": {}
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        let summaryText = try await MelixCLIRunner(
            client: StubControlPlaneXPCClient()
        ).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-nested-when",
                    dryRun: true
                )
            )
        )
        let summary = try #require(parseJSONObject(summaryText))
        let steps = try #require(summary["steps"] as? [[String: Any]])

        #expect(steps.first?["status"] as? String == "planned")
    }

    @Test("pipeline when equality rejects structurally different JSON values")
    func pipelineWhenEqualityRejectsStructurallyDifferentJSONValues() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("mismatched-when.pipeline.json")
        let receiptURL = root.appendingPathComponent("mismatched-when-receipts")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "mismatched-when",
          "inputs": {
            "null_gate": null,
            "array_gate": ["base"],
            "object_gate": {"name": "acceptance", "limit": 1},
            "bool_gate": true,
            "mixed_gate": ["base"]
          },
          "steps": [
            {
              "id": "null_match",
              "command": "model.roots.rescan",
              "when": {"input": "null_gate", "equals": null},
              "args": {}
            },
            {
              "id": "array_mismatch",
              "command": "model.roots.rescan",
              "when": {"input": "array_gate", "equals": ["base", "derived"]},
              "args": {}
            },
            {
              "id": "object_count_mismatch",
              "command": "model.roots.rescan",
              "when": {"input": "object_gate", "equals": {"name": "acceptance"}},
              "args": {}
            },
            {
              "id": "object_value_mismatch",
              "command": "model.roots.rescan",
              "when": {"input": "object_gate", "equals": {"name": "acceptance", "limit": 2}},
              "args": {}
            },
            {
              "id": "bool_type_mismatch",
              "command": "model.roots.rescan",
              "when": {"input": "bool_gate", "equals": "true"},
              "args": {}
            },
            {
              "id": "mixed_type_mismatch",
              "command": "model.roots.rescan",
              "when": {"input": "mixed_gate", "equals": {"0": "base"}},
              "args": {}
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        let summaryText = try await MelixCLIRunner(
            client: StubControlPlaneXPCClient()
        ).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-mismatched-when",
                    dryRun: true
                )
            )
        )
        let summary = try #require(parseJSONObject(summaryText))
        let steps = try #require(summary["steps"] as? [[String: Any]])
        let statuses = Dictionary(uniqueKeysWithValues: steps.compactMap { step -> (String, String)? in
            guard let id = step["id"] as? String,
                  let status = step["status"] as? String
            else {
                return nil
            }
            return (id, status)
        })

        #expect(statuses["null_match"] == "planned")
        #expect(statuses["array_mismatch"] == "skipped")
        #expect(statuses["object_count_mismatch"] == "skipped")
        #expect(statuses["object_value_mismatch"] == "skipped")
        #expect(statuses["bool_type_mismatch"] == "skipped")
        #expect(statuses["mixed_type_mismatch"] == "skipped")
    }

    @Test("pipeline rejects invalid check field types")
    func pipelineRejectsInvalidCheckFieldTypes() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let cases: [(name: String, checks: String, expected: String)] = [
            (
                "required-fields-string",
                #""required_result_fields": "model_id""#,
                "Pipeline step import checks.required_result_fields must be an array of strings."
            ),
            (
                "equals-array",
                #""equals": []"#,
                "Pipeline step import checks.equals must be a JSON object."
            ),
            (
                "artifact-path-number",
                #""artifact_path_exists": [1]"#,
                "Pipeline step import checks.artifact_path_exists must be an array of strings."
            ),
        ]

        for item in cases {
            let pipelineURL = root.appendingPathComponent("\(item.name).pipeline.json")
            try Data(
                """
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "\(item.name)",
                  "inputs": {},
                  "steps": [
                    {
                      "id": "import",
                      "command": "model.import",
                      "args": {
                        "path": "/tmp/model",
                        "model_id": "melix-dev-text"
                      },
                      "checks": {
                        \(item.checks)
                      }
                    }
                  ]
                }
                """.utf8
            )
            .write(to: pipelineURL)

            do {
                _ = try await MelixCLIRunner(client: StubControlPlaneXPCClient()).run(
                    .pipelineRun(
                        .init(
                            filePath: pipelineURL.path,
                            receiptDir: root.appendingPathComponent("\(item.name)-receipts").path,
                            traceID: "trace-\(item.name)",
                            dryRun: true
                        )
                    )
                )
                Issue.record("Expected invalid check case \(item.name) to fail.")
            } catch let error as MelixCLIError {
                #expect(error.localizedDescription == item.expected)
            }
        }
    }

    @Test("public model ops commands forward convert quantize and upload payloads")
    func publicModelOpsCommandsForwardConvertQuantizeAndUploadPayloads() async throws {
        let client = StubControlPlaneXPCClient()
        let runner = MelixCLIRunner(client: client)

        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-convert/convert.artifact",
                manifestJSON: #"{"job_id":"convert-job-1","operation":"convert","target_format":"melix_model_bundle"}"#
            )
        )
        let convertOutput = try await runner.run(
            .convert(
                .init(
                    modelID: "melix-dev-text",
                    outputDir: "/tmp/melix-convert",
                    targetFormat: "melix_model_bundle",
                    json: true
                )
            )
        )
        let convertCall = try #require(await client.lastModelOperationCall)
        let convertPayload = try #require(parseJSONObject(convertOutput))

        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-quantize/quantize.artifact",
                manifestJSON: #"{"job_id":"quantize-job-1","operation":"quantize","quant_profile_id":"q4"}"#
            )
        )
        let quantizeOutput = try await runner.run(
            .quantize(
                .init(
                    modelID: "melix-dev-text",
                    outputDir: "/tmp/melix-quantize",
                    quantProfileID: "q4",
                    weightQuant: "q4",
                    kvQuant: "q8",
                    quantizationMode: "qat",
                    sourceArtifactKind: "merged_adapter",
                    sourceArtifactPath: "/tmp/melix-export/merged",
                    quantizationBackend: "mlx_lm_convert",
                    mlxLMQBits: "4",
                    mlxLMQGroupSize: "128",
                    mlxLMQMode: "affine",
                    calibrationDatasetURI: "/tmp/melix-datasets/calibration",
                    qualityDelta: "-0.01",
                    latencyDelta: "-0.15",
                    localInferenceSmokeMode: "runtime_generate",
                    localInferenceSmokePrompt: "Reply with ISSUE365_OK",
                    json: true
                )
            )
        )
        let quantizeCall = try #require(await client.lastModelOperationCall)
        let quantizePayload = try #require(parseJSONObject(quantizeOutput))

        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-upload/upload.receipt.json",
                manifestJSON: #"{"job_id":"upload-job-1","operation":"upload","target_repo":"melix/models/demo"}"#
            )
        )
        let uploadOutput = try await runner.run(
            .upload(
                .init(
                    modelID: "melix-dev-text",
                    outputDir: "/tmp/melix-upload",
                    targetRepo: "melix/models/demo",
                    artifactPath: "/tmp/melix-convert/convert.artifact",
                    artifactKind: "converted_model_bundle",
                    artifactManifestPath: "/tmp/melix-convert/convert.artifact/manifest.json",
                    json: true
                )
            )
        )
        let uploadCall = try #require(await client.lastModelOperationCall)
        let uploadPayload = try #require(parseJSONObject(uploadOutput))

        #expect(convertPayload["job_id"] as? String == "convert-job-1")
        #expect(convertCall.operation == "convert")
        #expect(convertCall.outputDir == "/tmp/melix-convert")
        #expect(convertCall.ext["target_format"] == "melix_model_bundle")
        #expect(quantizePayload["job_id"] as? String == "quantize-job-1")
        #expect(quantizeCall.operation == "quantize")
        #expect(quantizeCall.outputDir == "/tmp/melix-quantize")
        #expect(quantizeCall.quantProfileID == "q4")
        #expect(quantizeCall.weightQuant == "q4")
        #expect(quantizeCall.kvQuant == "q8")
        #expect(quantizeCall.ext["quantization_mode"] == "qat")
        #expect(quantizeCall.ext["source_artifact_kind"] == "merged_adapter")
        #expect(quantizeCall.ext["source_artifact_path"] == "/tmp/melix-export/merged")
        #expect(quantizeCall.ext["quantization_backend"] == "mlx_lm_convert")
        #expect(quantizeCall.ext["mlx_lm_q_bits"] == "4")
        #expect(quantizeCall.ext["mlx_lm_q_group_size"] == "128")
        #expect(quantizeCall.ext["mlx_lm_q_mode"] == "affine")
        #expect(quantizeCall.ext["calibration_dataset_uri"] == "/tmp/melix-datasets/calibration")
        #expect(quantizeCall.ext["quality_delta"] == "-0.01")
        #expect(quantizeCall.ext["latency_delta"] == "-0.15")
        #expect(quantizeCall.ext["local_inference_smoke_mode"] == "runtime_generate")
        #expect(quantizeCall.ext["local_inference_smoke_prompt"] == "Reply with ISSUE365_OK")
        #expect(uploadPayload["job_id"] as? String == "upload-job-1")
        #expect(uploadCall.operation == "upload")
        #expect(uploadCall.outputDir == "/tmp/melix-upload")
        #expect(uploadCall.ext["target_repo"] == "melix/models/demo")
        #expect(uploadCall.ext["artifact_path"] == "/tmp/melix-convert/convert.artifact")
        #expect(uploadCall.ext["artifact_kind"] == "converted_model_bundle")
        #expect(uploadCall.ext["artifact_manifest_path"] == "/tmp/melix-convert/convert.artifact/manifest.json")
    }

    @Test("model hub download json renders a managed model receipt")
    func modelHubDownloadJSONRendersAManagedModelReceipt() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/hf-cache/models--mlx-community--Qwen3.5-0.8B-OptiQ-4bit/snapshots/abc123",
                manifestJSON: #"""
                {
                  "model_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                  "managed_model_path": "/tmp/hf-cache/models--mlx-community--Qwen3.5-0.8B-OptiQ-4bit/snapshots/abc123",
                  "ext": {
                    "melix.source_kind": "hub_repo",
                    "melix.source_locator": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    "melix.model_path": "/tmp/hf-cache/models--mlx-community--Qwen3.5-0.8B-OptiQ-4bit/snapshots/abc123"
                  }
                }
                """#
            )
        )

        let output = try await MelixCLIRunner(client: client).run(
            .modelHubDownload(.init(repoID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit", revision: "main", json: true))
        )
        let payload = try #require(parseJSONObject(output))

        #expect(payload["model_id"] as? String == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(
            payload["managed_model_path"] as? String ==
                "/tmp/hf-cache/models--mlx-community--Qwen3.5-0.8B-OptiQ-4bit/snapshots/abc123"
        )
        #expect(payload["source_kind"] as? String == "hub_repo")
        #expect(payload["source_locator"] as? String == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
    }

    @Test("model hub download caches Hugging Face token and reuses it without leaking output")
    func modelHubDownloadCachesHuggingFaceTokenAndReusesItWithoutLeakingOutput() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-hf-token-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let manifestJSON = #"""
        {
          "model_id": "mlx-community/Private-4bit",
          "managed_model_path": "/tmp/hf-cache/models--mlx-community--Private-4bit/snapshots/abc123",
          "output_path": "/tmp/hf-cache/models--mlx-community--Private-4bit/snapshots/abc123",
          "ext": {
            "melix.source_kind": "hub_repo",
            "melix.source_locator": "mlx-community/Private-4bit",
            "melix.model_path": "/tmp/hf-cache/models--mlx-community--Private-4bit/snapshots/abc123"
          }
        }
        """#
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            outputPath: "/tmp/hf-cache/models--mlx-community--Private-4bit/snapshots/abc123",
            manifestJSON: manifestJSON
        ))
        let runner = MelixCLIRunner(
            client: client,
            environment: ["MELIX_HOME": temporaryRoot.path]
        )

        let firstOutput = try await runner.run(
            .modelHubDownload(.init(repoID: "mlx-community/Private-4bit", revision: "main", hfToken: "hf_secret_token", json: true))
        )
        let firstCall = try #require(await client.lastModelOperationCall)
        let tokenFile = temporaryRoot
            .appendingPathComponent("secrets", isDirectory: true)
            .appendingPathComponent("huggingface-token.json")
        let tokenData = try Data(contentsOf: tokenFile)
        let tokenPayload = try #require(try JSONSerialization.jsonObject(with: tokenData) as? [String: Any])

        #expect(firstCall.ext["melix.hf_token"] == "hf_secret_token")
        #expect(tokenPayload["token"] as? String == "hf_secret_token")
        #expect((tokenPayload["masked_hint"] as? String)?.contains("hf_secret_token") == false)
        #expect(firstOutput.contains("hf_secret_token") == false)
        #expect(try posixPermissions(at: temporaryRoot.appendingPathComponent("secrets", isDirectory: true)) == 0o700)
        #expect(try posixPermissions(at: tokenFile) == 0o600)

        _ = try await runner.run(
            .modelHubDownload(.init(repoID: "mlx-community/Private-4bit", revision: "main", json: true))
        )
        let secondCall = try #require(await client.lastModelOperationCall)
        #expect(secondCall.ext["melix.hf_token"] == "hf_secret_token")
    }

    @Test("dataset list renders managed Hugging Face cache snapshots")
    func datasetListRendersManagedHuggingFaceCacheSnapshots() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: #"""
            {
              "operation": "dataset_snapshot",
              "dataset_registry": {
                "datasets": [
                  {
                    "repo_id": "Jax-dan/HundredCV-Chat",
                    "revision": "main",
                    "snapshot_id": "abc123",
                    "snapshot_path": "/tmp/hf-cache/datasets--Jax-dan--HundredCV-Chat/snapshots/abc123",
                    "total_bytes": 9007199254740993
                  }
                ],
                "roots": []
              }
            }
            """#
        ))

        let output = try await MelixCLIRunner(client: client).run(.datasetList(.init(json: false)))
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.operation == "dataset_snapshot")
        #expect(output.contains("repo_id\trevision\tsnapshot_id\ttotal_bytes\tsnapshot_path"))
        #expect(output.contains("Jax-dan/HundredCV-Chat\tmain\tabc123"))
        #expect(output.contains("\t8192.00 TB\t"))

        let jsonOutput = try await MelixCLIRunner(client: client).run(.datasetList(.init(json: true)))
        let jsonPayload = try #require(parseJSONObject(jsonOutput))
        let registry = try #require(jsonPayload["dataset_registry"] as? [String: Any])
        let datasets = try #require(registry["datasets"] as? [[String: Any]])
        #expect(datasets.first?["repo_id"] as? String == "Jax-dan/HundredCV-Chat")
    }

    @Test("dataset list renders empty managed dataset state")
    func datasetListRendersEmptyManagedDatasetState() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: #"{"operation":"dataset_snapshot","dataset_registry":{"datasets":[],"roots":[]}}"#
        ))

        let output = try await MelixCLIRunner(client: client).run(.datasetList(.init(json: false)))

        #expect(output == "No managed datasets found.\n")
    }

    @Test("dataset list surfaces malformed registry responses")
    func datasetListSurfacesMalformedRegistryResponses() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(manifestJSON: #"{"datasets":[]}"#))

        do {
            _ = try await MelixCLIRunner(client: client).run(.datasetList(.init(json: false)))
            Issue.record("Expected dataset list to throw for missing dataset_registry")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("dataset_snapshot response did not include a dataset_registry JSON object."))
        }
    }

    @Test("dataset hub download forwards dataset repo operation and redacts token from output")
    func datasetHubDownloadForwardsDatasetRepoOperationAndRedactsTokenFromOutput() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-hf-dataset-token-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            outputPath: "/tmp/hf-cache/datasets--Jax-dan--HundredCV-Chat/snapshots/abc123",
            manifestJSON: #"""
            {
              "dataset_id": "Jax-dan/HundredCV-Chat@main",
              "repo_id": "Jax-dan/HundredCV-Chat",
              "revision": "main",
              "snapshot_id": "abc123",
              "snapshot_path": "/tmp/hf-cache/datasets--Jax-dan--HundredCV-Chat/snapshots/abc123",
              "source_kind": "hf_cache_snapshot"
            }
            """#
        ))

        let runner = MelixCLIRunner(
            client: client,
            environment: ["MELIX_HOME": temporaryRoot.path]
        )
        let output = try await runner.run(
            .datasetHubDownload(.init(repoID: "Jax-dan/HundredCV-Chat", revision: "main", hfToken: "hf_secret_token", json: true))
        )
        let call = try #require(await client.lastModelOperationCall)
        let payload = try #require(parseJSONObject(output))

        #expect(call.modelID == "Jax-dan/HundredCV-Chat")
        #expect(call.operation == "dataset_download")
        #expect(call.ext["melix.source_kind"] == "hf_dataset")
        #expect(call.ext["melix.hf_dataset_repo_id"] == "Jax-dan/HundredCV-Chat")
        #expect(call.ext["melix.hf_revision"] == "main")
        #expect(call.ext["melix.hf_token"] == "hf_secret_token")
        #expect(payload["repo_id"] as? String == "Jax-dan/HundredCV-Chat")
        #expect(payload["managed_dataset_path"] as? String == "/tmp/hf-cache/datasets--Jax-dan--HundredCV-Chat/snapshots/abc123")
        #expect(output.contains("hf_secret_token") == false)

        _ = try await runner.run(
            .datasetHubDownload(.init(repoID: "Jax-dan/HundredCV-Chat", revision: "main", json: true))
        )
        let reusedTokenCall = try #require(await client.lastModelOperationCall)
        #expect(reusedTokenCall.ext["melix.hf_token"] == "hf_secret_token")
    }

    @Test("uri inspect classifies huggingface local and ambiguous sources")
    func uriInspectClassifiesSources() async throws {
        let runner = MelixCLIRunner(client: StubControlPlaneXPCClient())
        let hfOutput = try await runner.run(.uriInspect(.init(uri: "hf://model/mlx-community/Qwen3.5-0.8B-OptiQ-4bit", json: true)))
        let hfPayload = try #require(parseJSONObject(hfOutput))
        let hfCandidates = try #require(hfPayload["candidates"] as? [[String: Any]])
        #expect(hfCandidates.first?["kind"] as? String == "hf_model_repo")
        #expect(hfCandidates.first?["repo_id"] as? String == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect((hfPayload["metrics"] as? [String: Any])?["uri.candidate_count"] as? Double == 1)

        let ambiguousOutput = try await runner.run(.uriInspect(.init(uri: "org/repo", json: true)))
        let ambiguousPayload = try #require(parseJSONObject(ambiguousOutput))
        #expect(ambiguousPayload["candidate_count"] as? Int == 2)
        #expect(ambiguousPayload["ambiguity_count"] as? Int == 1)

        let datasetURLPayload = try #require(parseJSONObject(try await runner.run(.uriInspect(.init(
            uri: "https://huggingface.co/datasets/org/repo/tree/refs/pr/2?download=1",
            json: true
        )))))
        let datasetURLCandidate = try #require((datasetURLPayload["candidates"] as? [[String: Any]])?.first)
        #expect(datasetURLCandidate["kind"] as? String == "hf_dataset_repo")
        #expect(datasetURLCandidate["repo_id"] as? String == "org/repo")
        #expect(datasetURLCandidate["revision"] as? String == "refs/pr/2")
        #expect(datasetURLCandidate["normalized_locator"] as? String == "hf://dataset/org/repo@refs/pr/2")

        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-uri-inspect-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try "{}".write(to: root.appendingPathComponent("config.json"), atomically: true, encoding: .utf8)
        try Data([0]).write(to: root.appendingPathComponent("model.safetensors"))
        try "{}".write(to: root.appendingPathComponent("manifest.json"), atomically: true, encoding: .utf8)

        let localOutput = try await runner.run(.uriInspect(.init(uri: root.path, json: true)))
        let localPayload = try #require(parseJSONObject(localOutput))
        let localCandidates = try #require(localPayload["candidates"] as? [[String: Any]])
        let localKinds = Set(localCandidates.compactMap { $0["kind"] as? String })
        #expect(localKinds.contains("local_mlx_model_directory"))
        #expect(localKinds.contains("local_dataset_package"))
        #expect(localPayload["ambiguity_count"] as? Int == 1)

        let unresolvedOutput = try await runner.run(.uriImport(.init(uri: root.appendingPathComponent("missing").path, dryRun: true, json: true)))
        let unresolvedPayload = try #require(parseJSONObject(unresolvedOutput))
        #expect(unresolvedPayload["status"] as? String == "unresolved")
    }

    @Test("workflow recipes list show validate and plan")
    func workflowRecipesListShowValidateAndPlan() async throws {
        let outputRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-recipe-plan-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: outputRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: outputRoot) }

        let runner = MelixCLIRunner(
            client: StubControlPlaneXPCClient(),
            environment: ["MELIX_HOME": outputRoot.path]
        )
        let listPayload = try #require(parseJSONObject(try await runner.run(.recipesList(.init(task: "model_import", json: true)))))
        let recipes = try #require(listPayload["recipes"] as? [[String: Any]])
        #expect(recipes.contains { $0["id"] as? String == "import.hf-mlx-model" })

        let showPayload = try #require(parseJSONObject(try await runner.run(.recipesShow(.init(recipeID: "import.hf-mlx-model", json: true)))))
        #expect(showPayload["schema_version"] as? String == "melix.workflow_recipe.v1")
        #expect(showPayload["recipe_digest"] as? String != "")

        let validatePayload = try #require(parseJSONObject(try await runner.run(.recipesValidate(.init(target: "import.hf-mlx-model", json: true)))))
        #expect(validatePayload["valid"] as? Bool == true)

        let pipelineURL = outputRoot.appendingPathComponent("planned.pipeline.json")
        let planPayload = try #require(parseJSONObject(try await runner.run(.recipesPlan(
            .init(
                recipeID: "import.hf-mlx-model",
                values: ["repo_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"],
                outputPath: pipelineURL.path,
                json: true
            )
        ))))
        let pipeline = try #require(planPayload["pipeline"] as? [String: Any])
        let steps = try #require(pipeline["steps"] as? [[String: Any]])
        #expect(pipeline["schema_version"] as? String == "melix.pipeline.v1")
        #expect(steps.map { $0["command"] as? String } == ["estimate.import", "model.hub.download", "model.roots.rescan"])
        #expect(FileManager.default.fileExists(atPath: pipelineURL.path))
    }

    @Test("workflow recipe apply dry run writes pipeline receipts")
    func workflowRecipeApplyDryRunWritesPipelineReceipts() async throws {
        let melixHome = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-recipe-apply-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: melixHome, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: melixHome) }

        let runner = MelixCLIRunner(
            client: StubControlPlaneXPCClient(),
            environment: ["MELIX_HOME": melixHome.path]
        )
        let output = try await runner.run(.recipesApply(
            .init(
                recipeID: "import.hf-mlx-model",
                values: ["repo_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"],
                dryRun: true,
                json: true
            )
        ))
        let payload = try #require(parseJSONObject(output))
        #expect(payload["schema_version"] as? String == "melix.pipeline.run.v1")
        #expect(payload["status"] as? String == "planned")
        let recipe = try #require(payload["recipe"] as? [String: Any])
        #expect(recipe["id"] as? String == "import.hf-mlx-model")
        let steps = try #require(payload["steps"] as? [[String: Any]])
        #expect(steps.count == 3)
        let receiptDir = try #require(payload["receipt_dir"] as? String)
        #expect(FileManager.default.fileExists(atPath: receiptDir))
        #expect((payload["metrics"] as? [String: Any])?["recipe.apply_start_ms"] as? Double != nil)
        #expect((payload["metrics"] as? [String: Any])?["recipe.apply_retained_runs"] as? Int == 1)

        let recipeRoot = melixHome
            .appendingPathComponent("workflow-recipes", isDirectory: true)
            .appendingPathComponent("import.hf-mlx-model", isDirectory: true)
        for _ in 0..<22 {
            _ = try await runner.run(.recipesApply(
                .init(
                    recipeID: "import.hf-mlx-model",
                    values: ["repo_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"],
                    dryRun: true,
                    json: true
                )
            ))
        }
        let runDirectories = try FileManager.default.contentsOfDirectory(
            at: recipeRoot,
            includingPropertiesForKeys: [.isDirectoryKey]
        ).filter { url in
            UUID(uuidString: url.lastPathComponent) != nil
        }
        #expect(runDirectories.count == 20)
    }

    @Test("workflow recipe init rejects unmatched tasks")
    func workflowRecipeInitRejectsUnmatchedTasks() async throws {
        let runner = MelixCLIRunner(client: StubControlPlaneXPCClient())

        await #expect(throws: MelixCLIError.runtime("No workflow recipe matches task missing_task.")) {
            try await runner.run(.recipesInit(.init(
                sourceURI: "hf://model/mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                task: "missing_task",
                json: true
            )))
        }
    }

    @Test("dataset remove forwards safe snapshot selector")
    func datasetRemoveForwardsSafeSnapshotSelector() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            outputPath: "/tmp/melix/model-ops/dataset_remove.json",
            manifestJSON: #"{"operation":"dataset_remove","repo_id":"Jax-dan/HundredCV-Chat","snapshot_id":"abc123"}"#
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .datasetRemove(.init(repoID: "Jax-dan/HundredCV-Chat", revision: "main", snapshotID: "abc123", json: false))
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(output == "/tmp/melix/model-ops/dataset_remove.json\n")
        #expect(call.operation == "dataset_remove")
        #expect(call.modelID == "Jax-dan/HundredCV-Chat")
        #expect(call.ext["melix.hf_dataset_repo_id"] == "Jax-dan/HundredCV-Chat")
        #expect(call.ext["melix.hf_revision"] == "main")
        #expect(call.ext["melix.hf_snapshot_id"] == "abc123")
    }

    @Test("dataset remove renders manifest summary when worker output path is empty")
    func datasetRemoveRendersManifestSummaryWhenWorkerOutputPathIsEmpty() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            outputPath: "",
            manifestJSON: #"""
            {
              "operation": "dataset_remove",
              "repo_id": "Jax-dan/HundredCV-Chat",
              "revision": "main",
              "removed_snapshot_id": "abc123",
              "removed_snapshot_path": "/tmp/hf-cache/datasets--Jax-dan--HundredCV-Chat/snapshots/abc123"
            }
            """#
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .datasetRemove(.init(repoID: "Jax-dan/HundredCV-Chat", revision: "main", snapshotID: "abc123", json: false))
        )

        #expect(output.contains("Removed dataset snapshot Jax-dan/HundredCV-Chat@main (abc123)."))
        #expect(output.contains("Removed path: /tmp/hf-cache/datasets--Jax-dan--HundredCV-Chat/snapshots/abc123"))

        await client.setModelOperationResult(makeModelOperationResult(
            outputPath: "",
            manifestJSON: #"{"operation":"dataset_remove","repo_id":"Jax-dan/HundredCV-Chat","revision":"main","snapshot_id":"abc123"}"#
        ))
        let summaryWithoutPath = try await MelixCLIRunner(client: client).run(
            .datasetRemove(.init(repoID: "Jax-dan/HundredCV-Chat", revision: "main", snapshotID: "abc123", json: false))
        )
        #expect(summaryWithoutPath == "Removed dataset snapshot Jax-dan/HundredCV-Chat@main (abc123).\n")

        await client.setModelOperationResult(makeModelOperationResult(outputPath: "", manifestJSON: "not-json"))
        let genericSummary = try await MelixCLIRunner(client: client).run(
            .datasetRemove(.init(repoID: "Jax-dan/HundredCV-Chat", revision: "main", snapshotID: "abc123", json: false))
        )
        #expect(genericSummary == "Dataset removal completed.\n")
    }

    @Test("model import forwards a local import operation and renders a managed model receipt")
    func modelImportForwardsALocalImportOperationAndRendersAManagedModelReceipt() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-managed/local/melix-dev-qwen-local/main",
                manifestJSON: #"""
                {
                  "model_id": "melix-dev-qwen-local",
                  "ext": {
                    "melix.source_kind": "local_path",
                    "melix.source_locator": "/tmp/qwen-local-model"
                  }
                }
                """#
            )
        )

        let output = try await MelixCLIRunner(client: client).run(
            .modelImport(
                .init(
                    path: "/tmp/qwen-local-model",
                    modelID: "melix-dev-qwen-local",
                    modelKind: "text",
                    revision: "main",
                    json: true
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)
        let payload = try #require(parseJSONObject(output))

        #expect(call.modelID == "melix-dev-qwen-local")
        #expect(call.operation == "local_import")
        #expect(call.ext["source_path"] == "/tmp/qwen-local-model")
        #expect(call.ext["melix.source_kind"] == "local_path")
        #expect(call.ext["melix.model_kind"] == "text")
        #expect(call.ext["melix.revision"] == "main")
        #expect(payload["model_id"] as? String == "melix-dev-qwen-local")
        #expect(payload["managed_model_path"] as? String == "/tmp/melix-managed/local/melix-dev-qwen-local/main")
        #expect(payload["source_kind"] as? String == "local_path")
        #expect(payload["source_locator"] as? String == "/tmp/qwen-local-model")
    }

    @Test("chat run collects streamed assistant text and returns a typed json receipt")
    func chatRunCollectsStreamedAssistantTextAndReturnsATypedJSONReceipt() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setChatExecution(
            requestID: "chat-run-1",
            modelID: "melix-dev-qwen-local",
            events: [
                .tokenDelta("Echo: "),
                .tokenDelta("Reply with BASE_OK"),
                .completed(finishReason: "stop", assistantText: "", reasoningText: ""),
            ]
        )

        let output = try await MelixCLIRunner(client: client).run(
            .chatRun(
                .init(
                    modelID: "melix-dev-qwen-local",
                    message: "Reply with BASE_OK",
                    systemPrompt: "Be terse.",
                    serverSessionID: "server-session-1",
                    json: true
                )
            )
        )
        let request = try #require(await client.lastChatRequest)
        let payload = try #require(parseJSONObject(output))

        #expect(
            request ==
                ControlPlaneChatRequest(
                    modelID: "melix-dev-qwen-local",
                    messages: [
                        .init(role: "system", content: "Be terse."),
                        .init(role: "user", content: "Reply with BASE_OK"),
                    ]
                )
        )
        #expect(payload["model_id"] as? String == "melix-dev-qwen-local")
        #expect(payload["server_session_id"] as? String == "server-session-1")
        #expect(payload["assistant_text"] as? String == "Echo: Reply with BASE_OK")
        #expect(payload["finish_reason"] as? String == "stop")
        #expect(payload["request_id"] as? String == "chat-run-1")
    }

    @Test("remote server commands persist secrets and feed chat and evaluation targets")
    func remoteServerCommandsPersistSecretsAndFeedChatAndEvaluationTargets() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-remote-server-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let client = StubControlPlaneXPCClient()
        await client.setChatExecution(
            requestID: "remote-chat-1",
            modelID: "kimi-2.6",
            events: [
                .tokenDelta("remote ok"),
                .completed(finishReason: "stop", assistantText: "", reasoningText: ""),
            ]
        )
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-remote-1",
                suiteID: "event_extraction",
                datasetID: "top200",
                metricName: "eval.event_extraction.weighted_f1",
                metricValue: 0.5
            ),
        ])
        let runner = MelixCLIRunner(
            client: client,
            environment: ["MELIX_HOME": temporaryRoot.path]
        )
        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])

        #expect(try await runner.run(.remoteServerList(.init())) == "No remote servers configured.\n")

        let addOutput = try await runner.run(
            .remoteServerAdd(
                .init(
                    remoteServerID: "kimi",
                    title: "Kimi",
                    providerPreset: .kimi,
                    providerKind: "openai-compatible",
                    baseURL: "https://api.kimi.com/coding/v1",
                    defaultModelID: "kimi-2.6",
                    apiKey: "sk-kimi-secret-value",
                    timeoutSeconds: 42,
                    rateLimitPerMinute: 9,
                    json: true
                )
            )
        )
        let added = try #require(parseJSONObject(addOutput))
        #expect(added["id"] as? String == "kimi")
        #expect(added["provider_preset"] as? String == "kimi")
        #expect(addOutput.contains("sk-kimi-secret-value") == false)
        #expect(try RemoteServerAPIKeyStore(melixHome: melixHome).loadAPIKey(remoteServerID: "kimi")?.apiKey == "sk-kimi-secret-value")

        let listOutput = try await runner.run(.remoteServerList(.init()))
        #expect(listOutput.contains("remote_server_id\ttitle\tprovider\tprovider_kind\tdefault_model_id\thealth\tapi_key"))
        #expect(listOutput.contains("kimi\tKimi\tkimi\topenai-compatible\tkimi-2.6"))
        let listJSONOutput = try await runner.run(.remoteServerList(.init(json: true)))
        let listed = try #require(parseJSONArray(listJSONOutput))
        #expect(listed.count == 1)

        await #expect(throws: MelixCLIError.runtime("--base-url cannot be used with remote server kimi because provider kimi uses https://api.kimi.com/coding/v1.")) {
            try await runner.run(
                .remoteServerUpdate(
                    .init(
                        remoteServerID: "kimi",
                        baseURL: "https://override.example/v1"
                    )
                )
            )
        }

        let updateOutput = try await runner.run(
            .remoteServerUpdate(
                .init(
                    remoteServerID: "kimi",
                    title: "Kimi Updated",
                    defaultModelID: "kimi-2.6-chat",
                    apiKey: "sk-new-secret-value",
                    timeoutSeconds: 43,
                    rateLimitPerMinute: 10,
                    json: true
                )
            )
        )
        let updated = try #require(parseJSONObject(updateOutput))
        #expect(updated["title"] as? String == "Kimi Updated")
        #expect(updated["default_model_id"] as? String == "kimi-2.6-chat")
        #expect(try RemoteServerAPIKeyStore(melixHome: melixHome).loadAPIKey(remoteServerID: "kimi")?.apiKey == "sk-new-secret-value")

        let testOutput = try await runner.run(.remoteServerTest(.init(remoteServerID: "kimi", remoteModelID: "kimi-2.6", json: true)))
        let testPayload = try #require(parseJSONObject(testOutput))
        let testRequest = try #require(await client.lastChatRequest)
        #expect(testPayload["remote_server_id"] as? String == "kimi")
        #expect(testPayload["remote_model_id"] as? String == "kimi-2.6")
        #expect(testPayload["ok"] as? Bool == true)
        #expect(testRequest.remoteTarget?.apiKey == "sk-new-secret-value")
        #expect(testRequest.messages == [.init(role: "user", content: "Reply with OK.")])

        let plainTestOutput = try await runner.run(.remoteServerTest(.init(remoteServerID: "kimi", remoteModelID: "kimi-2.6")))
        #expect(plainTestOutput == "Remote server kimi responded with stop.\n")

        let chatOutput = try await runner.run(
            .chatRun(
                .init(
                    remoteServerID: "kimi",
                    remoteModelID: "",
                    message: "extract events",
                    systemPrompt: "Return JSON.",
                    json: true
                )
            )
        )
        let chatPayload = try #require(parseJSONObject(chatOutput))
        let chatRequest = try #require(await client.lastChatRequest)
        #expect(chatPayload["model_id"] as? String == "kimi-2.6")
        #expect(chatPayload["assistant_text"] as? String == "remote ok")
        #expect(chatRequest.remoteTarget?.serverID == "kimi")
        #expect(chatRequest.remoteTarget?.modelID == "kimi-2.6-chat")
        #expect(chatRequest.remoteTarget?.timeoutSeconds == 43)
        #expect(chatRequest.remoteTarget?.rateLimitPerMinute == 10)
        #expect(chatRequest.messages == [
            .init(role: "system", content: "Return JSON."),
            .init(role: "user", content: "extract events"),
        ])

        _ = try await runner.run(
            .evalRun(
                .init(
                    remoteServerID: "kimi",
                    remoteModelID: "",
                    suites: ["event_extraction"],
                    datasetID: "top200",
                    sampleSize: 3,
                    profile: .init(scoringMode: "event_extraction_weighted_f1"),
                    json: true
                )
            )
        )
        let evaluationRequest = try #require((await client.evaluationRequests).first)
        #expect(evaluationRequest.remoteTarget?.remoteServerID == "kimi")
        #expect(evaluationRequest.remoteTarget?.modelID == "kimi-2.6-chat")
        #expect(evaluationRequest.remoteTarget?.apiKey == "sk-new-secret-value")
        #expect(evaluationRequest.remoteTarget?.baseURL == "https://api.kimi.com/coding/v1")

        let removeOutput = try await runner.run(.remoteServerRemove(.init(remoteServerID: "kimi", json: true)))
        let removed = try #require(parseJSONObject(removeOutput))
        #expect(removed["removed_id"] as? String == "kimi")
        #expect(try RemoteServerAPIKeyStore(melixHome: melixHome).loadAPIKey(remoteServerID: "kimi") == nil)
        #expect(try await runner.run(.remoteServerList(.init())) == "No remote servers configured.\n")
    }

    @Test("eval run forwards semantic judge remote target as transient parameters")
    func evalRunForwardsSemanticJudgeRemoteTargetAsTransientParameters() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-semantic-judge-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-semantic-judge",
                suiteID: "event_extraction",
                datasetID: "top200",
                metricName: "eval.event_extraction.weighted_f1",
                metricValue: 0.5
            ),
        ])
        let runner = MelixCLIRunner(
            client: client,
            environment: ["MELIX_HOME": temporaryRoot.path]
        )

        _ = try await runner.run(
            .remoteServerAdd(
                .init(
                    remoteServerID: "evaluated",
                    title: "Evaluated",
                    providerPreset: .custom,
                    providerKind: "openai-compatible",
                    baseURL: "https://evaluated.example/v1",
                    defaultModelID: "evaluated-default",
                    apiKey: "sk-evaluated",
                    timeoutSeconds: 30,
                    rateLimitPerMinute: 0
                )
            )
        )
        _ = try await runner.run(
            .remoteServerAdd(
                .init(
                    remoteServerID: "judge",
                    title: "Judge",
                    providerPreset: .custom,
                    providerKind: "openai-compatible",
                    baseURL: "https://judge.example/v1",
                    defaultModelID: "judge-default",
                    apiKey: "sk-judge",
                    timeoutSeconds: 41,
                    rateLimitPerMinute: 12
                )
            )
        )

        _ = try await runner.run(
            MelixCLICommand.evalRun(
                EvalRunOptions(
                    remoteServerID: "evaluated",
                    remoteModelID: "evaluated-model",
                    suites: ["event_extraction"],
                    sampleSize: 3,
                    source: .localJSONL(path: "/Users/ChenYu/Downloads/top200_final.jsonl"),
                    profile: .init(scoringMode: "event_extraction_weighted_f1"),
                    parameters: [
                        "remote_provider_extra_body_json": "{\"max_tokens\":1024,\"chat_template_kwargs\":{\"enable_thinking\":false}}",
                    ],
                    semanticJudgeRemoteServerID: "judge",
                    semanticJudgeModelID: "judge-model",
                    json: true
                )
            )
        )

        let request = try #require((await client.evaluationRequests).first)
        #expect(request.remoteTarget?.remoteServerID == "evaluated")
        #expect(request.remoteTarget?.modelID == "evaluated-model")
        #expect(request.remoteTarget?.apiKey == "sk-evaluated")
        #expect(request.parameters["semantic_judge_remote_server_id"] == "judge")
        #expect(request.parameters["semantic_judge_provider_kind"] == "openai-compatible")
        #expect(request.parameters["semantic_judge_base_url"] == "https://judge.example/v1")
        #expect(request.parameters["semantic_judge_api_key"] == "sk-judge")
        #expect(request.parameters["semantic_judge_model_id"] == "judge-model")
        #expect(request.parameters["semantic_judge_timeout_seconds"] == "41")
        #expect(request.parameters["semantic_judge_rate_limit_per_minute"] == "12")
        #expect(request.parameters["remote_provider_extra_body_json"] == "{\"max_tokens\":1024,\"chat_template_kwargs\":{\"enable_thinking\":false}}")

        await #expect(throws: MelixCLIError.runtime("Semantic judge scoring is only supported for event_extraction_weighted_f1.")) {
            try await runner.run(
                MelixCLICommand.evalRun(
                    EvalRunOptions(
                        remoteServerID: "evaluated",
                        remoteModelID: "evaluated-model",
                        suites: ["mmlu"],
                        source: .localJSONL(path: "/tmp/eval.jsonl"),
                        fieldMapping: .init(inputTextPath: "prompt", targetPath: "answer"),
                        profile: .init(scoringMode: "multiple_choice_accuracy"),
                        semanticJudgeRemoteServerID: "judge",
                        semanticJudgeModelID: "judge-model",
                        json: true
                    )
                )
            )
        }
    }

    @Test("remote server commands surface missing records and credentials")
    func remoteServerCommandsSurfaceMissingRecordsAndCredentials() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-remote-server-errors-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let runner = MelixCLIRunner(
            client: StubControlPlaneXPCClient(),
            environment: ["MELIX_HOME": temporaryRoot.path]
        )

        await #expect(throws: MelixCLIError.runtime("Remote server missing was not found.")) {
            try await runner.run(.remoteServerUpdate(.init(remoteServerID: "missing", title: "Missing")))
        }
        await #expect(throws: MelixCLIError.runtime("Remote server missing was not found.")) {
            try await runner.run(.remoteServerTest(.init(remoteServerID: "missing")))
        }

        _ = try await runner.run(
            .remoteServerAdd(
                .init(
                    remoteServerID: "custom",
                    title: "Custom",
                    providerPreset: .custom,
                    providerKind: "openai-compatible",
                    baseURL: "https://sub2api.example/v1",
                    defaultModelID: "remote-model"
                )
            )
        )

        await #expect(throws: MelixCLIError.runtime("Remote server custom has no API key configured.")) {
            try await runner.run(.remoteServerTest(.init(remoteServerID: "custom")))
        }
    }

    @Test("evaluation prompt commands persist drafts freeze revisions and feed eval run")
    func evaluationPromptCommandsPersistDraftsFreezeRevisionsAndFeedEvalRun() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-eval-prompts-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        let promptFile = temporaryRoot.appendingPathComponent("prompt.txt")
        try "Extract only scheduled events.".write(to: promptFile, atomically: true, encoding: .utf8)

        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-prompt-1",
                suiteID: "event_extraction",
                datasetID: "top200",
                metricName: "eval.event_extraction.overall_weighted_f1",
                metricValue: 0.5
            ),
        ])
        let runner = MelixCLIRunner(
            client: client,
            environment: ["MELIX_HOME": temporaryRoot.path]
        )

        let listOutput = try await runner.run(.evalPromptList(.init()))
        #expect(listOutput.contains(EvaluationPromptStore.builtInBaselinePromptID))
        #expect(listOutput.contains("read-only"))

        let createOutput = try await runner.run(
            .evalPromptCreate(
                .init(
                    promptID: "event-prod",
                    title: "Event Prod",
                    systemPromptFile: promptFile.path,
                    json: true
                )
            )
        )
        let created = try #require(parseJSONObject(createOutput))
        #expect(created["id"] as? String == "event-prod")
        #expect(created["latest_revision_id"] as? String == "rev-1")

        let listJSONOutput = try await runner.run(.evalPromptList(.init(json: true)))
        let listedPrompts = try #require(parseJSONArray(listJSONOutput))
        #expect(listedPrompts.contains { (($0 as? [String: Any])?["id"] as? String) == "event-prod" })

        await #expect(throws: MelixCLIError.runtime("Evaluation prompt event-prod revision rev-1 is not frozen.")) {
            _ = try await runner.run(
                .evalRun(
                    .init(
                        modelID: "melix-dev-text",
                        suites: ["event_extraction"],
                        source: .localJSONL(path: "/tmp/top200.jsonl"),
                        profile: .init(scoringMode: "event_extraction_weighted_f1"),
                        evalPromptID: "event-prod"
                    )
                )
            )
        }

        await #expect(throws: MelixCLIError.runtime("Evaluation prompt missing-prompt was not found.")) {
            _ = try await runner.run(.evalPromptShow(.init(promptID: "missing-prompt")))
        }

        try "Extract established events and future plans.".write(to: promptFile, atomically: true, encoding: .utf8)
        let updateOutput = try await runner.run(.evalPromptUpdate(.init(promptID: "event-prod", systemPromptFile: promptFile.path, json: true)))
        let updated = try #require(parseJSONObject(updateOutput))
        #expect(updated["latest_revision_id"] as? String == "rev-1")

        let freezeOutput = try await runner.run(.evalPromptFreeze(.init(promptID: "event-prod", json: true)))
        let frozen = try #require(parseJSONObject(freezeOutput))
        let revisions = try #require(frozen["revisions"] as? [[String: Any]])
        #expect(revisions.first?["status"] as? String == "frozen")

        await #expect(throws: MelixCLIError.runtime("Evaluation prompt event-prod revision missing-rev was not found.")) {
            _ = try await runner.run(.evalPromptShow(.init(promptID: "event-prod", revisionID: "missing-rev")))
        }

        let showOutput = try await runner.run(.evalPromptShow(.init(promptID: "event-prod")))
        #expect(showOutput.contains("prompt_id=event-prod"))
        #expect(showOutput.contains("system_prompt:"))

        let showJSONOutput = try await runner.run(.evalPromptShow(.init(promptID: "event-prod", json: true)))
        let showJSON = try #require(parseJSONObject(showJSONOutput))
        #expect(showJSON["prompt_id"] as? String == "event-prod")

        let textCreateOutput = try await runner.run(
            .evalPromptCreate(.init(promptID: "event-text", title: "Event Text", systemPromptFile: promptFile.path))
        )
        #expect(textCreateOutput.contains("event-text"))
        try "Text prompt update.".write(to: promptFile, atomically: true, encoding: .utf8)
        let textUpdateOutput = try await runner.run(
            .evalPromptUpdate(.init(promptID: "event-text", systemPromptFile: promptFile.path))
        )
        #expect(textUpdateOutput.contains("event-text"))
        let textFreezeOutput = try await runner.run(.evalPromptFreeze(.init(promptID: "event-text")))
        #expect(textFreezeOutput.contains("frozen"))
        let textArchiveJSONOutput = try await runner.run(.evalPromptArchive(.init(promptID: "event-text", json: true)))
        let archivedTextPrompt = try #require(parseJSONObject(textArchiveJSONOutput))
        #expect(archivedTextPrompt["archived"] as? Bool == true)

        _ = try await runner.run(
            .evalRun(
                .init(
                    modelID: "melix-dev-text",
                    suites: ["event_extraction"],
                    datasetID: "top200",
                    sampleSize: 3,
                    source: .localJSONL(path: "/tmp/top200.jsonl"),
                    profile: .init(scoringMode: "event_extraction_weighted_f1"),
                    evalPromptID: "event-prod",
                    json: true
                )
            )
        )
        let request = try #require((await client.evaluationRequests).first)
        #expect(request.parameters["prompt_id"] == "event-prod")
        #expect(request.parameters["prompt_revision_id"] == "rev-1")
        #expect(request.parameters["prompt_content_hash"]?.hasPrefix("sha256:") == true)
        #expect(request.parameters["eval_prompt_system_prompt"] == "Extract established events and future plans.")
        #expect(request.parameters["eval_prompt_examples_json"] == "[]")

        let archiveOutput = try await runner.run(.evalPromptArchive(.init(promptID: "event-prod")))
        #expect(archiveOutput == "Archived evaluation prompt event-prod.\n")
    }

    @Test("chat run surfaces stream failures as runtime errors")
    func chatRunSurfacesStreamFailuresAsRuntimeErrors() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setChatExecution(
            requestID: "chat-run-failed",
            modelID: "melix-dev-qwen-local",
            events: [
                .failed(code: "unavailable", message: "server session is not ready"),
            ]
        )

        await #expect(throws: MelixCLIError.runtime("melix chat run failed [unavailable]: server session is not ready")) {
            try await MelixCLIRunner(client: client).run(
                .chatRun(
                    .init(
                        modelID: "melix-dev-qwen-local",
                        message: "Reply with BASE_OK",
                        systemPrompt: "",
                        serverSessionID: "server-session-1",
                        json: true
                    )
                )
            )
        }
    }

    @Test("chat run returns plain text output when json is disabled")
    func chatRunReturnsPlainTextOutputWhenJSONIsDisabled() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setChatExecution(
            requestID: "chat-run-plain",
            modelID: "melix-dev-qwen-local",
            events: [
                .tokenDelta("Echo: Reply with BASE_OK"),
                .completed(finishReason: "stop", assistantText: "", reasoningText: ""),
            ]
        )

        let output = try await MelixCLIRunner(client: client).run(
            .chatRun(
                .init(
                    modelID: "melix-dev-qwen-local",
                    message: "Reply with BASE_OK",
                    systemPrompt: "",
                    serverSessionID: "server-session-1",
                    json: false
                )
            )
        )

        #expect(output == "Echo: Reply with BASE_OK\n")
    }

    @Test("chat run tolerates non-terminal events and falls back to streamed text when completion is omitted")
    func chatRunFallsBackToStreamedTextWhenCompletionIsOmitted() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setChatExecution(
            requestID: "chat-run-fallback",
            modelID: "melix-dev-qwen-local",
            events: [
                .heartbeat,
                .tokenDelta("Echo: Reply with BASE_OK"),
            ]
        )

        let output = try await MelixCLIRunner(client: client).run(
            .chatRun(
                .init(
                    modelID: "melix-dev-qwen-local",
                    message: "Reply with BASE_OK",
                    systemPrompt: "",
                    serverSessionID: "server-session-1",
                    json: false
                )
            )
        )

        #expect(output == "Echo: Reply with BASE_OK\n")
    }

    @Test("chat run rejects completed streams without any assistant text")
    func chatRunRejectsCompletedStreamsWithoutAnyAssistantText() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setChatExecution(
            requestID: "chat-run-empty",
            modelID: "melix-dev-qwen-local",
            events: [
                .completed(finishReason: "stop", assistantText: "", reasoningText: ""),
            ]
        )

        await #expect(throws: MelixCLIError.runtime("melix chat run did not produce assistant text.")) {
            try await MelixCLIRunner(client: client).run(
                .chatRun(
                    .init(
                        modelID: "melix-dev-qwen-local",
                        message: "Reply with BASE_OK",
                        systemPrompt: "",
                        serverSessionID: "server-session-1",
                        json: true
                    )
                )
            )
        }
    }

    @Test("model import forwards the managed root override when configured")
    func modelImportForwardsTheManagedRootOverrideWhenConfigured() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-managed/local/melix-dev-qwen-local/main",
                manifestJSON: #"""
                {
                  "model_id": "melix-dev-qwen-local",
                  "ext": {
                    "melix.source_kind": "local_path",
                    "melix.source_locator": "/tmp/qwen-local-model"
                  }
                }
                """#
            )
        )

        _ = try await MelixCLIRunner(
            client: client,
            environment: ["MELIX_MANAGED_MODEL_ROOT": "/tmp/melix-managed"]
        ).run(
            .modelImport(
                .init(
                    path: "/tmp/qwen-local-model",
                    modelID: "melix-dev-qwen-local",
                    modelKind: "text",
                    revision: "main"
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.ext["melix.managed_root"] == "/tmp/melix-managed")
    }

    @Test("model import json rejects a malformed managed model manifest")
    func modelImportJSONRejectsAMalformedManagedModelManifest() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-managed/local/melix-dev-qwen-local/main",
                manifestJSON: "not-json"
            )
        )

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .modelImport(
                    .init(
                        path: "/tmp/qwen-local-model",
                        modelID: "melix-dev-qwen-local",
                        modelKind: "text",
                        revision: "main",
                        json: true
                    )
                )
            )
            Issue.record("Expected model import json to reject malformed managed model manifests.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("Managed model operations must return a JSON manifest."))
        }
    }

    @Test("model import json falls back to source model and source path fields")
    func modelImportJSONFallsBackToSourceModelAndSourcePathFields() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-managed/local/melix-dev-qwen-local/main",
                manifestJSON: #"""
                {
                  "source_model": "melix-dev-qwen-local",
                  "source_path": "/tmp/qwen-local-model"
                }
                """#
            )
        )

        let output = try await MelixCLIRunner(client: client).run(
            .modelImport(
                .init(
                    path: "/tmp/qwen-local-model",
                    modelID: "melix-dev-qwen-local",
                    modelKind: "text",
                    revision: "main",
                    json: true
                )
            )
        )
        let payload = try #require(parseJSONObject(output))

        #expect(payload["model_id"] as? String == "melix-dev-qwen-local")
        #expect(payload["managed_model_path"] as? String == "/tmp/melix-managed/local/melix-dev-qwen-local/main")
        #expect(payload["source_kind"] as? String == "")
        #expect(payload["source_locator"] as? String == "/tmp/qwen-local-model")
    }

    @Test("model import json requires a model identifier in the managed manifest")
    func modelImportJSONRequiresAModelIdentifierInTheManagedManifest() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-managed/local/melix-dev-qwen-local/main",
                manifestJSON: #"{"warnings":["manifest missing model id"]}"#
            )
        )

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .modelImport(
                    .init(
                        path: "/tmp/qwen-local-model",
                        modelID: "melix-dev-qwen-local",
                        modelKind: "text",
                        revision: "main",
                        json: true
                    )
                )
            )
            Issue.record("Expected model import json to require a model identifier in the managed manifest.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("Managed model manifest did not include a model identifier and output path."))
        }
    }

    @Test("model roots rescan omits an empty registry-root override")
    func modelRootsRescanOmitsEmptyRegistryRootOverride() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-runner-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer {
            try? FileManager.default.removeItem(at: temporaryRoot)
        }

        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(manifestJSON: #"{"model_registry":{"models":[],"roots":[]}}"#))
        let store = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        )

        _ = try await MelixCLIRunner(client: client, operatorSessionStore: store).run(
            .modelRootsRescan(.init())
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.operation == "registry_snapshot")
        #expect(call.ext["melix.registry_rescan"] == "true")
        #expect(call.ext["melix.registry_roots_json"] == nil)
    }

    @Test("model list surfaces runtime_mode as a first-class column in JSON and text output")
    func modelListSurfacesRuntimeModeColumn() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-runner-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: #"{"model_registry":{"models":[],"roots":[]}}"#
        ))
        // Seed a mix of base, fused, and adapter-backed models to prove the
        // list renderer distinguishes all three via the runtime_mode column.
        await client.setServerSnapshot(makeServerSnapshot(models: [
            makeModelSummary(id: "melix-base-text", kind: "text"),
            makeModelSummary(
                id: "melix-base-text-lora-fused",
                kind: "text",
                runtimeMode: "fused_derived_model",
                activationMode: "fused_derived_model"
            ),
            makeModelSummary(
                id: "melix-base-text-lora-runtime",
                kind: "text",
                runtimeMode: "adapter_backed_runtime",
                activationMode: "adapter_backed_runtime"
            ),
        ]))
        let store = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        )
        try store.save(
            MelixOperatorSessionState(
                selectedServerSessionID: "",
                serverSessions: [],
                registryRoots: []
            )
        )

        // JSON output: every entry carries runtime_mode, and adapter-backed
        // entries additionally echo activation_mode for backward compat.
        let jsonOutput = try await MelixCLIRunner(client: client, operatorSessionStore: store).run(
            .modelList(.init(json: true))
        )
        let jsonData = try #require(jsonOutput.data(using: .utf8))
        let entries = try #require(try JSONSerialization.jsonObject(with: jsonData) as? [[String: Any]])
        let byID = Dictionary(uniqueKeysWithValues: entries.compactMap { entry -> (String, [String: Any])? in
            guard let id = entry["model_id"] as? String else { return nil }
            return (id, entry)
        })
        #expect(byID["melix-base-text"]?["runtime_mode"] as? String == "")
        #expect(byID["melix-base-text-lora-fused"]?["runtime_mode"] as? String == "fused_derived_model")
        #expect(byID["melix-base-text-lora-runtime"]?["runtime_mode"] as? String == "adapter_backed_runtime")
        #expect(byID["melix-base-text-lora-runtime"]?["activation_mode"] as? String == "adapter_backed_runtime")
        // Base models have no activation_mode in settings.ext so the field
        // is omitted from the payload rather than blank-strung.
        #expect(byID["melix-base-text"]?["activation_mode"] == nil)

        // Text output: fixed-width table with header row and short-form
        // runtime tags. Header column names are upper-case for legibility;
        // columns are padded to max width with two-space separators.
        let textOutput = try await MelixCLIRunner(client: client, operatorSessionStore: store).run(
            .modelList(.init(json: false))
        )
        let lines = textOutput.split(separator: "\n").map(String.init)
        let header = try #require(lines.first)
        // Header exposes all four columns in padded fixed-width order.
        #expect(header.contains("MODEL_ID"))
        #expect(header.contains("KIND"))
        #expect(header.contains("STATE"))
        #expect(header.contains("STATUS"))
        #expect(header.contains("RUNTIME"))
        // Each short-form runtime tag appears exactly once on a data row.
        // Use ``hasPrefix`` on the model_id + trailing space to unambiguously
        // pick each row even if another id were a superstring.
        let dataRows = lines.dropFirst()
        let baseRow = try #require(
            dataRows.first(where: { $0.hasPrefix("melix-base-text ") && $0.hasSuffix("-") })
        )
        let fusedRow = try #require(
            dataRows.first(where: { $0.hasPrefix("melix-base-text-lora-fused ") && $0.hasSuffix("fused") })
        )
        let adapterRow = try #require(
            dataRows.first(where: { $0.hasPrefix("melix-base-text-lora-runtime") && $0.hasSuffix("adapter") })
        )
        // The first column is padded to the widest model_id
        // ("melix-base-text-lora-runtime" = 28 chars); assert the "KIND"
        // column actually starts at the column-separator offset. A
        // regression that dropped padding would collapse the gap.
        let firstColumnWidth = "melix-base-text-lora-runtime".count
        let separator = "  "
        let kindColumnOffset = firstColumnWidth + separator.count
        for row in [baseRow, fusedRow, adapterRow] {
            let indexAtKindStart = row.index(row.startIndex, offsetBy: kindColumnOffset)
            let kindPrefix = row[indexAtKindStart...].prefix(4)
            #expect(kindPrefix == "text", "row not padded at column offset: \(row)")
        }
    }

    @Test("model list surfaces missing managed Hugging Face cache status")
    func modelListSurfacesMissingManagedHuggingFaceCacheStatus() async throws {
        var missingModel = makeModelSummary(id: "mlx-community/Qwen3-0.6B-4bit", kind: "text")
        missingModel.settings.ext["melix.model_path_missing"] = "true"
        missingModel.settings.ext["melix.model_path"] = "/tmp/hf-cache/models--mlx-community--Qwen3-0.6B-4bit/snapshots/missing"
        missingModel.settings.ext["melix.registry_descriptor_path"] = "/tmp/melix-managed/huggingface/mlx-community/Qwen3-0.6B-4bit/main"
        missingModel.settings.ext["melix.hf_repo_id"] = "mlx-community/Qwen3-0.6B-4bit"
        missingModel.settings.ext["melix.hf_revision"] = "main"
        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(models: [missingModel]))
        let runner = MelixCLIRunner(client: client)

        let textOutput = try await runner.run(.modelList(.init(json: false)))
        let jsonOutput = try await runner.run(.modelList(.init(json: true)))
        let jsonData = try #require(jsonOutput.data(using: .utf8))
        let entries = try #require(try JSONSerialization.jsonObject(with: jsonData) as? [[String: Any]])
        let entry = try #require(entries.first)

        #expect(textOutput.contains("STATUS"))
        #expect(textOutput.contains("missing-cache"))
        #expect(entry["runtime_status"] as? String == "missing-cache")
        #expect(entry["model_path_missing"] as? Bool == true)
        #expect(entry["model_path"] as? String == "/tmp/hf-cache/models--mlx-community--Qwen3-0.6B-4bit/snapshots/missing")
        #expect(entry["registry_descriptor_path"] as? String == "/tmp/melix-managed/huggingface/mlx-community/Qwen3-0.6B-4bit/main")
        #expect(entry["restore_command"] as? String == "melix model hub download --repo-id mlx-community/Qwen3-0.6B-4bit --revision main")
    }

    @Test("model list primes configured registry roots before fetching the server snapshot")
    func modelListPrimesConfiguredRegistryRootsBeforeFetchingServerSnapshot() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-runner-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer {
            try? FileManager.default.removeItem(at: temporaryRoot)
        }

        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: #"{"model_registry":{"models":[],"roots":[]}}"#
        ))
        await client.setServerSnapshot(makeServerSnapshot(models: [
            makeModelSummary(id: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit", kind: "text"),
        ]))
        let store = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        )
        try store.save(
            MelixOperatorSessionState(
                selectedServerSessionID: "",
                serverSessions: [],
                registryRoots: ["/tmp/model-root-a"]
            )
        )

        let output = try await MelixCLIRunner(client: client, operatorSessionStore: store).run(
            .modelList(.init(json: true))
        )
        let call = try #require(await client.lastModelOperationCall)
        let outputData = try #require(output.data(using: .utf8))
        let models = try #require(try JSONSerialization.jsonObject(with: outputData) as? [[String: Any]])
        let firstModel = try #require(models.first)
        let rootsJSON = try #require(call.ext["melix.registry_roots_json"])
        let rootsData = try #require(rootsJSON.data(using: .utf8))
        let roots = try #require(try JSONSerialization.jsonObject(with: rootsData) as? [String])

        #expect(call.operation == "registry_snapshot")
        #expect(call.ext["melix.registry_rescan"] == "true")
        #expect(roots == ["/tmp/model-root-a"])
        #expect(firstModel["model_id"] as? String == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
    }

    @Test("model inspect primes registry snapshot even without configured roots")
    func modelInspectPrimesRegistrySnapshotWithoutConfiguredRoots() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-runner-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer {
            try? FileManager.default.removeItem(at: temporaryRoot)
        }

        let importedModelID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: #"{"model_registry":{"models":[],"roots":[]}}"#
        ))
        await client.setModelInfo(
            modelID: importedModelID,
            info: {
                var info = Melix_Controlplane_V1_ModelInfo()
                info.ok = true
                info.modelKind = "text"
                info.supportedModalities = ["text"]
                info.supportedTasks = ["generate"]
                return info
            }()
        )
        let store = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        )

        _ = try await MelixCLIRunner(client: client, operatorSessionStore: store).run(
            .modelInspect(.init(modelID: importedModelID, json: true))
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.modelID == "melix-dev-text")
        #expect(call.operation == "registry_snapshot")
        #expect(call.ext["melix.registry_rescan"] == "true")
        #expect(call.ext["melix.registry_roots_json"] == nil)
    }

    @Test("model inspect reports missing managed Hugging Face cache recovery fields")
    func modelInspectReportsMissingManagedHuggingFaceCacheRecoveryFields() async throws {
        var missingModel = makeModelSummary(id: "mlx-community/Qwen3-0.6B-4bit", kind: "text")
        missingModel.settings.ext["melix.model_path_missing"] = "true"
        missingModel.settings.ext["melix.model_path"] = "/tmp/hf-cache/models--mlx-community--Qwen3-0.6B-4bit/snapshots/missing"
        missingModel.settings.ext["melix.registry_descriptor_path"] = "/tmp/melix-managed/huggingface/mlx-community/Qwen3-0.6B-4bit/main"
        missingModel.settings.ext["melix.hf_repo_id"] = "mlx-community/Qwen3-0.6B-4bit"
        missingModel.settings.ext["melix.hf_revision"] = "main"
        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(models: [missingModel]))
        await client.setModelInfo(
            modelID: "mlx-community/Qwen3-0.6B-4bit",
            info: {
                var info = Melix_Controlplane_V1_ModelInfo()
                info.ok = true
                info.modelKind = "text"
                info.supportedTasks = ["generate"]
                return info
            }()
        )
        let runner = MelixCLIRunner(client: client)

        let textOutput = try await runner.run(
            .modelInspect(.init(modelID: "mlx-community/Qwen3-0.6B-4bit", json: false))
        )
        let jsonOutput = try await runner.run(
            .modelInspect(.init(modelID: "mlx-community/Qwen3-0.6B-4bit", json: true))
        )
        let jsonData = try #require(jsonOutput.data(using: .utf8))
        let payload = try #require(try JSONSerialization.jsonObject(with: jsonData) as? [String: Any])

        #expect(textOutput.contains("runtime_status=missing cache"))
        #expect(textOutput.contains("runtime_path=/tmp/hf-cache/models--mlx-community--Qwen3-0.6B-4bit/snapshots/missing"))
        #expect(textOutput.contains("descriptor_path=/tmp/melix-managed/huggingface/mlx-community/Qwen3-0.6B-4bit/main"))
        #expect(textOutput.contains("restore_command=melix model hub download --repo-id mlx-community/Qwen3-0.6B-4bit --revision main"))
        #expect(payload["model_path_missing"] as? Bool == true)
        #expect(payload["runtime_status"] as? String == "missing-cache")
        #expect(payload["model_path"] as? String == "/tmp/hf-cache/models--mlx-community--Qwen3-0.6B-4bit/snapshots/missing")
        #expect(payload["registry_descriptor_path"] as? String == "/tmp/melix-managed/huggingface/mlx-community/Qwen3-0.6B-4bit/main")
        #expect(payload["restore_command"] as? String == "melix model hub download --repo-id mlx-community/Qwen3-0.6B-4bit --revision main")
    }

    @Test("model load and chat run map missing cache errors to the stable CLI code")
    func modelLoadAndChatRunMapMissingCacheErrorsToStableCLICode() async throws {
        let loadClient = StubControlPlaneXPCClient()
        await loadClient.setLoadError(
            ControlPlaneXPCClientError.requestFailed(
                code: "model_runtime_missing",
                message: "Hugging Face cache files are missing. Re-download this model to restore it."
            )
        )

        do {
            _ = try await MelixCLIRunner(client: loadClient).run(
                .modelLoad(.init(modelID: "melix-dev-text"))
            )
            Issue.record("Expected model load to fail with missing cache")
        } catch let error as MelixCLIError {
            #expect(error.errorDescription == "Hugging Face cache files are missing. Re-download this model to restore it.")
            #expect(MelixCLIJSONEnvelope.code(for: error) == "model_runtime_missing")
        } catch {
            Issue.record("Unexpected model load error: \(error)")
        }

        let chatClient = StubControlPlaneXPCClient()
        await chatClient.setChatError(
            ControlPlaneChatExecutionError.requestFailed(
                code: "model_runtime_missing",
                message: "Hugging Face cache files are missing. Re-download this model to restore it."
            )
        )
        do {
            _ = try await MelixCLIRunner(client: chatClient).run(
                .chatRun(.init(modelID: "mlx-community/Qwen3-0.6B-4bit", message: "hello"))
            )
            Issue.record("Expected chat run to fail with missing cache")
        } catch let error as MelixCLIError {
            #expect(error.errorDescription == "Hugging Face cache files are missing. Re-download this model to restore it.")
            #expect(MelixCLIJSONEnvelope.code(for: error) == "model_runtime_missing")
        } catch {
            Issue.record("Unexpected chat run error: \(error)")
        }
    }

    @Test("server lifecycle commands forward session ids and render updated snapshots")
    func serverLifecycleCommandsForwardSessionIDsAndRenderUpdatedSnapshots() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot())

        let startOutput = try await MelixCLIRunner(client: client).run(
            .serverStart(.init(serverSessionID: "server-session-2"))
        )
        let resumeOutput = try await MelixCLIRunner(client: client).run(
            .serverResume(.init(serverSessionID: "server-session-2", json: true))
        )
        let wakeOutput = try await MelixCLIRunner(client: client).run(
            .serverWake(.init(serverSessionID: "server-session-2", json: true))
        )
        let stopOutput = try await MelixCLIRunner(client: client).run(
            .serverStop(.init(serverSessionID: "server-session-2"))
        )

        let wakePayload = try #require(parseJSONObject(wakeOutput))
        let wakeSessions = try #require(wakePayload["runtime_sessions"] as? [[String: Any]])
        let wakeSession = try #require(wakeSessions.first)

        #expect(startOutput.contains("server_ready\tserver-session-2\tready\tactive\toperator_resume"))
        #expect(resumeOutput.contains(#""wake_reason" : "operator_resume""#))
        #expect(wakeSession["wake_reason"] as? String == "request_activity")
        #expect(stopOutput.contains("server_stopped\tserver-session-2\tstopped\tstopped\trequest_activity"))
        #expect(await client.lastServerAction == .stop("server-session-2"))
    }

    @Test("server pause forwards the target session and returns json output")
    func serverPauseForwardsTargetSessionAndReturnsJSON() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(runtimeSessions: [makeRuntimeSession()]))

        let output = try await MelixCLIRunner(client: client).run(
            .serverPause(.init(serverSessionID: "server-session-1", json: true))
        )
        let action = try #require(await client.lastServerAction)
        let payload = try #require(parseJSONObject(output))
        let runtimeSessions = try #require(payload["runtime_sessions"] as? [[String: Any]])
        let firstSession = try #require(runtimeSessions.first)

        #expect(action == .pause("server-session-1"))
        #expect(payload["server_state"] as? String == "server_degraded")
        #expect(firstSession["server_session_id"] as? String == "server-session-1")
        #expect(firstSession["lifecycle_state"] as? String == "paused")
        #expect(firstSession["power_state"] as? String == "active")
    }

    @Test("server idle policy forwards thresholds and returns updated runtime metadata")
    func serverIdlePolicyForwardsThresholdsAndReturnsUpdatedRuntimeMetadata() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(runtimeSessions: [makeRuntimeSession()]))

        let output = try await MelixCLIRunner(client: client).run(
            .serverSetIdlePolicy(
                .init(
                    serverSessionID: "server-session-1",
                    autoSleepEnabled: true,
                    lightSleepAfterSeconds: 60,
                    deepSleepAfterSeconds: 600,
                    json: true
                )
            )
        )
        let call = try #require(await client.lastIdlePolicyCall)
        let payload = try #require(parseJSONObject(output))
        let runtimeSessions = try #require(payload["runtime_sessions"] as? [[String: Any]])
        let firstSession = try #require(runtimeSessions.first)

        #expect(call.serverSessionID == "server-session-1")
        #expect(call.autoSleepEnabled)
        #expect(call.lightSleepAfterSeconds == 60)
        #expect(call.deepSleepAfterSeconds == 600)
        #expect(firstSession["auto_sleep_enabled"] as? Bool == true)
        #expect(firstSession["light_sleep_after_seconds"] as? Int == 60)
        #expect(firstSession["deep_sleep_after_seconds"] as? Int == 600)
    }

    @Test("server session commands persist shared operator state and start validates serveable bindings")
    func serverSessionCommandsPersistSharedOperatorStateAndStartValidatesServeableBindings() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-runner-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer {
            try? FileManager.default.removeItem(at: temporaryRoot)
        }

        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(models: [
            makeModelSummary(id: "melix-dev-image", kind: "image"),
            makeModelSummary(id: "melix-dev-vlm", kind: "vlm"),
        ]))
        let store = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        )
        let runner = MelixCLIRunner(client: client, operatorSessionStore: store)

        _ = try await runner.run(
            .serverSessionCreate(
                .init(
                    title: "Vision Session",
                    servedModelIDs: ["melix-dev-vlm"],
                    host: "127.0.0.1",
                    port: 12434,
                    accelerationMode: "speculative_decode",
                    draftModelID: "z-lab/Qwen3.5-27B-DFlash",
                    numDraftTokens: 4
                )
            )
        )
        _ = try await runner.run(
            .serverSessionSelect(.init(serverSessionID: "server-session-1"))
        )
        let listOutput = try await runner.run(.serverSessionList(.init(json: true)))

        let payload = try #require(parseJSONObject(listOutput))
        let selectedServerSessionID = try #require(payload["selected_server_session_id"] as? String)
        let sessions = try #require(payload["server_sessions"] as? [[String: Any]])

        #expect(selectedServerSessionID == "server-session-1")
        #expect(sessions.count == 1)
        #expect(sessions.first?["default_model_id"] as? String == "melix-dev-vlm")
        #expect(sessions.first?["served_model_ids"] as? [String] == ["melix-dev-vlm"])

        _ = try await runner.run(
            .serverStart(.init(serverSessionID: "server-session-1"))
        )

        let gatewayConfigCall = try #require(await client.lastGatewayConfigApplyRequest)
        let servingDefaultsCall = try #require(await client.lastServingDefaultsApplyRequest)

        #expect(gatewayConfigCall.serverSessionID == "server-session-1")
        #expect(gatewayConfigCall.defaultModelID == "melix-dev-vlm")
        #expect(gatewayConfigCall.servedModelIDs == ["melix-dev-vlm"])
        #expect(servingDefaultsCall.serverSessionID == "server-session-1")
        #expect(servingDefaultsCall.accelerationMode == .speculativeDecode)
        #expect(servingDefaultsCall.draftModelID == "z-lab/Qwen3.5-27B-DFlash")
        #expect(servingDefaultsCall.numDraftTokens == 4)

        try await store.save(
            MelixOperatorSessionState(
                selectedSurfaceID: "server",
                selectedToolSectionID: "modelsLibrary",
                selectedServerSessionID: "server-session-1",
                serverSessions: [
                    .init(
                        id: "server-session-1",
                        title: "Broken Session",
                        defaultModelID: "melix-dev-ocr",
                        servedModelIDs: ["melix-dev-ocr"]
                    )
                ]
            )
        )
        await client.setServerSnapshot(makeServerSnapshot(models: [
            makeModelSummary(id: "melix-dev-ocr", kind: "ocr"),
        ]))

        await #expect(throws: MelixCLIError.self) {
            _ = try await runner.run(.serverStart(.init(serverSessionID: "server-session-1")))
        }
    }

    @Test("server session update persists draft serving defaults for start")
    func serverSessionUpdatePersistsDraftServingDefaultsForStart() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-runner-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer {
            try? FileManager.default.removeItem(at: temporaryRoot)
        }

        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(models: [
            makeModelSummary(id: "mlx-community/Qwen3.5-27B-4bit", kind: "text"),
        ]))
        let store = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        )
        let runner = MelixCLIRunner(client: client, operatorSessionStore: store)

        _ = try await runner.run(
            .serverSessionCreate(
                .init(
                    title: "Qwen Session",
                    servedModelIDs: ["mlx-community/Qwen3.5-27B-4bit"]
                )
            )
        )
        _ = try await runner.run(
            .serverSessionUpdate(
                .init(
                    serverSessionID: "server-session-1",
                    draftModelID: "z-lab/Qwen3.5-27B-DFlash"
                )
            )
        )
        _ = try await runner.run(
            .serverStart(.init(serverSessionID: "server-session-1"))
        )

        let servingDefaultsCall = try #require(await client.lastServingDefaultsApplyRequest)
        #expect(servingDefaultsCall.accelerationMode == .speculativeDecode)
        #expect(servingDefaultsCall.draftModelID == "z-lab/Qwen3.5-27B-DFlash")
        #expect(servingDefaultsCall.numDraftTokens == 4)
    }

    @Test("server start shortcut creates a titled session and starts the generated id")
    func serverStartShortcutCreatesTitledSessionAndStartsGeneratedID() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-runner-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer {
            try? FileManager.default.removeItem(at: temporaryRoot)
        }

        let modelID = "mlx-community/gemma-4-31b-it-4bit"
        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(models: [
            makeModelSummary(id: modelID, kind: "text"),
        ]))
        let store = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        )
        let runner = MelixCLIRunner(client: client, operatorSessionStore: store)

        _ = try await runner.run(
            .serverStart(
                .init(
                    serverTitle: "Gemma 31B",
                    servedModelIDs: [modelID],
                    host: "127.0.0.1",
                    port: 12434,
                    rateLimitPerMinute: 60,
                    timeoutSeconds: 240
                )
            )
        )

        let state = try #require(try store.load())
        let session = try #require(state.serverSessions.first)
        let gatewayConfigCall = try #require(await client.lastGatewayConfigApplyRequest)
        let servingDefaultsCall = try #require(await client.lastServingDefaultsApplyRequest)
        let startedAction = try #require(await client.lastServerAction)

        #expect(state.selectedServerSessionID == "server-session-1")
        #expect(session.id == "server-session-1")
        #expect(session.title == "Gemma 31B")
        #expect(session.defaultModelID == modelID)
        #expect(session.servedModelIDs == [modelID])
        #expect(session.host == "127.0.0.1")
        #expect(session.port == 12434)
        #expect(session.rateLimitPerMinute == 60)
        #expect(session.timeoutSeconds == 240)
        #expect(gatewayConfigCall.serverSessionID == "server-session-1")
        #expect(gatewayConfigCall.defaultModelID == modelID)
        #expect(gatewayConfigCall.servedModelIDs == [modelID])
        #expect(gatewayConfigCall.port == 12434)
        #expect(servingDefaultsCall.serverSessionID == "server-session-1")
        #expect(startedAction == .start("server-session-1"))
    }

    @Test("server start shortcut reuses an existing titled session")
    func serverStartShortcutReusesExistingTitledSession() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-runner-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer {
            try? FileManager.default.removeItem(at: temporaryRoot)
        }

        let originalModelID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        let updatedModelID = "mlx-community/gemma-4-31b-it-4bit"
        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(models: [
            makeModelSummary(id: originalModelID, kind: "text"),
            makeModelSummary(id: updatedModelID, kind: "text"),
        ]))
        let store = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        )
        try store.save(
            MelixOperatorSessionState(
                selectedSurfaceID: "server",
                selectedToolSectionID: "modelsLibrary",
                selectedServerSessionID: "server-session-1",
                serverSessions: [
                    .init(
                        id: "server-session-1",
                        title: "Qwen Dev",
                        defaultModelID: originalModelID,
                        servedModelIDs: [originalModelID],
                        host: "127.0.0.1",
                        port: 8080
                    ),
                ]
            )
        )

        _ = try await MelixCLIRunner(client: client, operatorSessionStore: store).run(
            .serverStart(
                .init(
                    serverTitle: "Qwen Dev",
                    servedModelIDs: [updatedModelID],
                    host: "0.0.0.0",
                    port: 12435,
                    rateLimitPerMinute: 90,
                    timeoutSeconds: 300
                )
            )
        )

        let state = try #require(try store.load())
        let session = try #require(state.serverSessions.first)
        let gatewayConfigCall = try #require(await client.lastGatewayConfigApplyRequest)
        let startedAction = try #require(await client.lastServerAction)

        #expect(state.serverSessions.count == 1)
        #expect(state.selectedServerSessionID == "server-session-1")
        #expect(session.id == "server-session-1")
        #expect(session.title == "Qwen Dev")
        #expect(session.defaultModelID == updatedModelID)
        #expect(session.servedModelIDs == [updatedModelID])
        #expect(session.host == "0.0.0.0")
        #expect(session.port == 12435)
        #expect(session.rateLimitPerMinute == 90)
        #expect(session.timeoutSeconds == 300)
        #expect(gatewayConfigCall.serverSessionID == "server-session-1")
        #expect(gatewayConfigCall.defaultModelID == updatedModelID)
        #expect(gatewayConfigCall.servedModelIDs == [updatedModelID])
        #expect(gatewayConfigCall.port == 12435)
        #expect(startedAction == .start("server-session-1"))
    }

    @Test("server start shortcut allocates the first available generated id")
    func serverStartShortcutAllocatesFirstAvailableGeneratedID() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-runner-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer {
            try? FileManager.default.removeItem(at: temporaryRoot)
        }

        let modelID = "mlx-community/gemma-4-31b-it-4bit"
        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(models: [
            makeModelSummary(id: modelID, kind: "text"),
        ]))
        let store = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        )
        try store.save(
            MelixOperatorSessionState(
                selectedSurfaceID: "server",
                selectedToolSectionID: "modelsLibrary",
                selectedServerSessionID: "server-session-3",
                serverSessions: [
                    .init(
                        id: "server-session-1",
                        title: "Existing One",
                        defaultModelID: modelID,
                        servedModelIDs: [modelID]
                    ),
                    .init(
                        id: "server-session-3",
                        title: "Existing Three",
                        defaultModelID: modelID,
                        servedModelIDs: [modelID]
                    ),
                ]
            )
        )

        _ = try await MelixCLIRunner(client: client, operatorSessionStore: store).run(
            .serverStart(
                .init(
                    serverTitle: "Gemma 31B",
                    servedModelIDs: [modelID],
                    port: 12434
                )
            )
        )

        let state = try #require(try store.load())
        let created = try #require(state.serverSessions.first(where: { $0.title == "Gemma 31B" }))
        let startedAction = try #require(await client.lastServerAction)

        #expect(created.id == "server-session-2")
        #expect(state.selectedServerSessionID == "server-session-2")
        #expect(startedAction == .start("server-session-2"))
    }

    @Test("server start shortcut requires title and model arguments")
    func serverStartShortcutRequiresTitleAndModelArguments() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-runner-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer {
            try? FileManager.default.removeItem(at: temporaryRoot)
        }

        let runner = MelixCLIRunner(
            client: StubControlPlaneXPCClient(),
            operatorSessionStore: MelixOperatorSessionStore(
                melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
            )
        )

        await #expect(throws: MelixCLIError.missingRequired("TITLE is required when passing --model, --models, --default-model, --host, --port, --rate-limit-per-minute, --timeout-seconds, or --model-idle-timeout-seconds to melix server start.")) {
            _ = try await runner.run(.serverStart(.init(servedModelIDs: ["mlx-community/gemma-4-31b-it-4bit"])))
        }
        await #expect(throws: MelixCLIError.missingRequired("--model or --models is required when starting a titled server session.")) {
            _ = try await runner.run(.serverStart(.init(serverTitle: "Gemma 31B")))
        }
    }

    @Test("server start falls back to model info when the snapshot omits an imported model")
    func serverStartFallsBackToModelInfoWhenSnapshotOmitsImportedModel() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-runner-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer {
            try? FileManager.default.removeItem(at: temporaryRoot)
        }

        let importedModelID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(models: []))
        await client.setModelInfo(
            modelID: importedModelID,
            info: {
                var info = Melix_Controlplane_V1_ModelInfo()
                info.ok = true
                info.modelKind = "text"
                info.supportedModalities = ["text"]
                info.supportedTasks = ["generate", "chat"]
                return info
            }()
        )

        let store = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        )
        try await store.save(
            MelixOperatorSessionState(
                selectedSurfaceID: "server",
                selectedToolSectionID: "modelsLibrary",
                selectedServerSessionID: "server-session-1",
                serverSessions: [
                    .init(
                        id: "server-session-1",
                        title: "Imported Session",
                        defaultModelID: importedModelID,
                        servedModelIDs: [importedModelID]
                    )
                ]
            )
        )

        _ = try await MelixCLIRunner(client: client, operatorSessionStore: store).run(
            .serverStart(.init(serverSessionID: "server-session-1"))
        )

        let gatewayConfigCall = try #require(await client.lastGatewayConfigApplyRequest)
        let startedAction = try #require(await client.lastServerAction)

        #expect(gatewayConfigCall.defaultModelID == importedModelID)
        #expect(gatewayConfigCall.servedModelIDs == [importedModelID])
        #expect(startedAction == .start("server-session-1"))
    }

    @Test("server snapshot renders empty sessions and fallback labels")
    func serverSnapshotRendersEmptySessionsAndFallbackLabels() async throws {
        let client = StubControlPlaneXPCClient()

        var emptySnapshot = Melix_Controlplane_V1_ServerSnapshot()
        emptySnapshot.serverState = .serverBooting
        await client.setServerSnapshot(emptySnapshot)
        let emptyOutput = try await MelixCLIRunner(client: client).run(.serverSnapshot(.init()))

        var loadingSession = makeRuntimeSession(serverSessionID: "server-session-loading")
        loadingSession.lifecycleState = .loading
        loadingSession.powerState = .lightSleep
        loadingSession.wakeReason = .toolActivity
        var stoppedSession = makeRuntimeSession(serverSessionID: "server-session-stopped")
        stoppedSession.lifecycleState = .stopped
        stoppedSession.powerState = .stopped
        stoppedSession.wakeReason = .policyApply
        var failedSession = makeRuntimeSession(serverSessionID: "server-session-failed")
        failedSession.lifecycleState = .error
        failedSession.powerState = .deepSleep
        failedSession.wakeReason = .operatorResume
        var unknownSession = makeRuntimeSession(serverSessionID: "server-session-unknown")
        unknownSession.lifecycleState = .UNRECOGNIZED(999)
        unknownSession.powerState = .UNRECOGNIZED(999)
        unknownSession.wakeReason = .UNRECOGNIZED(999)

        var richSnapshot = Melix_Controlplane_V1_ServerSnapshot()
        richSnapshot.serverState = .serverDraining
        richSnapshot.runtimeSessions = [loadingSession]
        await client.setServerSnapshot(richSnapshot)
        let loadingOutput = try await MelixCLIRunner(client: client).run(.serverSnapshot(.init()))

        richSnapshot.serverState = .serverStopped
        richSnapshot.runtimeSessions = [stoppedSession]
        await client.setServerSnapshot(richSnapshot)
        let stoppedOutput = try await MelixCLIRunner(client: client).run(.serverSnapshot(.init()))

        richSnapshot.serverState = .serverFailed
        richSnapshot.runtimeSessions = [failedSession]
        await client.setServerSnapshot(richSnapshot)
        let failedOutput = try await MelixCLIRunner(client: client).run(.serverSnapshot(.init()))

        richSnapshot.serverState = .UNRECOGNIZED(999)
        richSnapshot.runtimeSessions = [unknownSession]
        await client.setServerSnapshot(richSnapshot)
        let unknownOutput = try await MelixCLIRunner(client: client).run(.serverSnapshot(.init(json: true)))

        #expect(emptyOutput == "server_state=server_booting\nNo runtime sessions found.\n")
        #expect(loadingOutput.contains("server_draining\tserver-session-loading\tloading\tlight_sleep\ttool_activity"))
        #expect(stoppedOutput.contains("server_stopped\tserver-session-stopped\tstopped\tstopped\tpolicy_apply"))
        #expect(failedOutput.contains("server_failed\tserver-session-failed\terror\tdeep_sleep\toperator_resume"))
        #expect(unknownOutput.contains(#""server_state" : "server_state_unspecified""#))
        #expect(unknownOutput.contains(#""lifecycle_state" : "lifecycle_unspecified""#))
        #expect(unknownOutput.contains(#""power_state" : "power_unspecified""#))
        #expect(unknownOutput.contains(#""wake_reason" : "wake_unspecified""#))
    }

    @Test("lora list resolves the first text model and renders registry output")
    func loraListResolvesTextModelAndRendersRegistryOutput() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(models: [
            makeModelSummary(id: "melix-dev-image", kind: "image"),
            makeModelSummary(id: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit", kind: "text"),
        ]))
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: #"{"adapters":[{"adapter_name":"demo-adapter","status":"activated","source_model":"mlx-community/Qwen3.5-0.8B-OptiQ-4bit","activation_mode":"adapter_backed_runtime","derived_model_id":"melix-qwen35-runtime"}],"derived_models":[{"model_id":"melix-qwen35-runtime","derived_model_alias":"Runtime Alias","activation_mode":"adapter_backed_runtime","activation_backend":"internal","source_model":"mlx-community/Qwen3.5-0.8B-OptiQ-4bit"}],"experiment_groups":[{"group_id":"nightly-qwen35","run_count":2,"latest_preset_title":"Balanced Adapter","best_loss":0.33,"recommended_manifest_path":"/tmp/melix/train_lora/job-2/train_lora.adapter.json"}]}"#
        ))

        let output = try await MelixCLIRunner(client: client).run(.loraList(.init()))
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(call.operation == "registry_snapshot")
        #expect(output.contains("adapter\tstatus\tsource_model\tactivation_mode\tderived_model_id"))
        #expect(output.contains("demo-adapter\tactivated\tmlx-community/Qwen3.5-0.8B-OptiQ-4bit\tadapter_backed_runtime\tmelix-qwen35-runtime"))
        #expect(output.contains("derived_model_id\talias\tactivation_mode\tactivation_backend\tsource_model"))
        #expect(output.contains("melix-qwen35-runtime\tRuntime Alias\tadapter_backed_runtime\tinternal\tmlx-community/Qwen3.5-0.8B-OptiQ-4bit"))
        #expect(output.contains("experiment_group\truns\tpreset\tbest_loss\trecommended_manifest"))
        #expect(output.contains("nightly-qwen35\t2\tBalanced Adapter\t0.330\t/tmp/melix/train_lora/job-2/train_lora.adapter.json"))
    }

    @Test("lora list returns json when requested and honors an explicit preferred model id")
    func loraListReturnsJSONWhenRequested() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: #"{"adapters":[{"adapter_name":"demo-adapter"}]}"#
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraList(.init(modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit", json: true))
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        let payload = try #require(parseJSONObject(output))
        let adapters = try #require(payload["adapters"] as? [[String: Any]])
        #expect(adapters.count == 1)
        #expect(adapters.first?["adapter_name"] as? String == "demo-adapter")
        #expect(payload["experiment_groups"] as? [Any] != nil)
        #expect(payload["jobs"] == nil)
    }

    @Test("lora list falls back to raw manifest text when the registry payload is not tabular")
    func loraListFallsBackToRawManifestText() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(manifestJSON: "not-json"))

        let output = try await MelixCLIRunner(client: client).run(.loraList(.init()))

        #expect(output == "not-json")
    }

    @Test("lora list renders the empty adapter state when no adapters are present")
    func loraListRendersEmptyRegistryState() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(manifestJSON: #"{"adapters":[]}"#))

        let output = try await MelixCLIRunner(client: client).run(.loraList(.init()))

        #expect(output == "No adapters or derived models found.\n")
    }

    @Test("lora experiments list renders a fixed-width table")
    func loraExperimentsListRendersFixedWidthTable() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: makeExperimentsRegistryManifest()
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraExperimentsList(.init(modelID: "melix-dev-text"))
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.operation == "registry_snapshot")
        #expect(output.contains("GROUP_ID"))
        #expect(output.contains("TITLE"))
        #expect(output.contains("RUNS"))
        #expect(output.contains("BEST_LOSS"))
        #expect(output.contains("RESUME_READY"))
        #expect(output.contains("nightly-qwen35"))
        #expect(output.contains("Nightly Qwen35"))
        #expect(output.contains("2 of 3"))
    }

    @Test("lora experiments list emits JSON when requested")
    func loraExperimentsListEmitsJSON() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: makeExperimentsRegistryManifest()
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraExperimentsList(.init(modelID: "melix-dev-text", json: true))
        )

        let payload = try #require(parseJSONObject(output))
        let groups = try #require(payload["experiment_groups"] as? [[String: Any]])
        #expect(groups.count == 1)
        #expect(groups.first?["group_id"] as? String == "nightly-qwen35")
    }

    @Test("lora experiments show renders detail for a known group")
    func loraExperimentsShowRendersDetail() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: makeExperimentsRegistryManifest()
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraExperimentsShow(.init(modelID: "melix-dev-text", groupID: "nightly-qwen35"))
        )

        #expect(output.contains("Group: nightly-qwen35"))
        #expect(output.contains("Title: Nightly Qwen35"))
        #expect(output.contains("Runs (3):"))
        #expect(output.contains("RUN_ID"))
        #expect(output.contains("CHECKPOINTS"))
        #expect(output.contains("RESUME_READY"))
        #expect(output.contains("model-ops-0012"))
        #expect(output.contains("Best known adapter:"))
        #expect(output.contains("Manifest: /tmp/melix-train-lora/model-ops-0012/train_lora.adapter.json"))
        #expect(output.contains("Resume via: melix lora resume --group-id nightly-qwen35"))
        #expect(output.contains("\t") == false)
    }

    @Test("lora experiments list renders n/a when best loss is missing")
    func loraExperimentsListRendersNotAvailableBestLoss() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: makeExperimentsRegistryManifestWithoutBestLoss()
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraExperimentsList(.init(modelID: "melix-dev-text"))
        )

        #expect(output.contains("n/a"))
        #expect(output.contains("0.0000") == false)
    }

    @Test("lora experiments list surfaces a runtime error when snapshot JSON is malformed")
    func loraExperimentsListErrorsOnMalformedSnapshot() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(manifestJSON: "not-json-at-all"))

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .loraExperimentsList(.init(modelID: "melix-dev-text"))
            )
            Issue.record("Expected experiments list to throw for malformed JSON")
        } catch let error as MelixCLIError {
            if case .runtime(let message) = error {
                #expect(message.contains("registry_snapshot payload"))
            } else {
                Issue.record("Expected runtime error, got \(error)")
            }
        }
    }

    @Test("lora publishes list renders fixed-width table with export kind column")
    func loraPublishesListRendersFixedWidthTable() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: makePublishesRegistryManifest()
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraPublishesList(.init(modelID: "melix-dev-text"))
        )
        let call = try #require(await client.lastModelOperationCall)
        #expect(call.operation == "registry_snapshot")
        #expect(output.contains("JOB_ID"))
        #expect(output.contains("KIND"))
        #expect(output.contains("TARGET_REPO"))
        #expect(output.contains("SOURCE_JOB"))
        #expect(output.contains("ADAPTER/DERIVED"))
        #expect(output.contains("model-ops-0100"))
        #expect(output.contains("adapter_export"))
        #expect(output.contains("merged_export"))
        #expect(output.contains("melix/adapters/adapter-a"))
    }

    @Test("lora publishes list emits JSON when requested")
    func loraPublishesListEmitsJSON() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: makePublishesRegistryManifest()
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraPublishesList(.init(modelID: "melix-dev-text", json: true))
        )
        let payload = try #require(parseJSONObject(output))
        let publishes = try #require(payload["publishes"] as? [[String: Any]])
        #expect(publishes.count == 2)
    }

    @Test("lora publishes show renders detail with source lineage")
    func loraPublishesShowRendersDetail() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: makePublishesRegistryManifest()
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraPublishesShow(.init(modelID: "melix-dev-text", jobID: "model-ops-0100"))
        )

        #expect(output.contains("Publish: model-ops-0100"))
        #expect(output.contains("Export kind: adapter_export"))
        #expect(output.contains("Target repo: melix/adapters/adapter-a"))
        #expect(output.contains("Distribution contract: adapter_only"))
        #expect(output.contains("Source job: model-ops-0050"))
        #expect(output.contains("Adapter name: adapter-a"))
        #expect(output.contains("Published files"))
        #expect(output.contains("\t") == false)
    }

    @Test("lora publishes show renders processor config lineage for merged_multimodal artifacts")
    func loraPublishesShowRendersProcessorConfigLineage() async throws {
        let client = StubControlPlaneXPCClient()
        let manifest = #"""
        {
          "operation": "registry_snapshot",
          "publishes": [
            {
              "job_id": "model-ops-0200",
              "status": "published",
              "export_artifact_kind": "merged_export",
              "distribution_contract": "merged_multimodal",
              "target_repo": "melix/models/melix-dev-vlm",
              "source_artifact_kind": "derived_text_model",
              "processor_config_files": ["processor_config.json"],
              "published_files": ["manifest.json", "model.safetensors", "processor_config.json"]
            }
          ]
        }
        """#
        await client.setModelOperationResult(makeModelOperationResult(manifestJSON: manifest))

        let output = try await MelixCLIRunner(client: client).run(
            .loraPublishesShow(.init(modelID: "melix-dev-text", jobID: "model-ops-0200"))
        )

        #expect(output.contains("Export kind: merged_export"))
        #expect(output.contains("Distribution contract: merged_multimodal"))
        #expect(output.contains("Processor configs (1)"))
        #expect(output.contains("processor_config.json"))
        #expect(output.contains("\t") == false)
    }

    @Test("lora publishes show errors for an unknown job id and lists known ids")
    func loraPublishesShowErrorsForUnknownJob() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: makePublishesRegistryManifest()
        ))

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .loraPublishesShow(.init(modelID: "melix-dev-text", jobID: "missing"))
            )
            Issue.record("Expected publishes show to throw for an unknown job id")
        } catch let error as MelixCLIError {
            if case .missingRequired(let message) = error {
                #expect(message.contains("missing"))
                #expect(message.contains("model-ops-0100"))
            } else {
                Issue.record("Expected missingRequired error, got \(error)")
            }
        }
    }

    @Test("lora publishes show truncates the known-jobs list past 10 entries")
    func loraPublishesShowTruncatesKnownJobList() async throws {
        let client = StubControlPlaneXPCClient()
        let publishes = (1...15).map { index -> String in
            let jobID = "model-ops-\(String(format: "%04d", index))"
            return """
            {"job_id":"\(jobID)","status":"published","target_repo":"melix/adapters/\(jobID)","export_artifact_kind":"adapter_export"}
            """
        }.joined(separator: ",")
        let manifest = "{\"operation\":\"registry_snapshot\",\"publishes\":[\(publishes)]}"
        await client.setModelOperationResult(makeModelOperationResult(manifestJSON: manifest))

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .loraPublishesShow(.init(modelID: "melix-dev-text", jobID: "missing"))
            )
            Issue.record("Expected publishes show to throw for an unknown job id")
        } catch let error as MelixCLIError {
            if case .missingRequired(let message) = error {
                #expect(message.contains("… (5 more)"))
                #expect(message.contains("model-ops-0001"))
                // 11th+ jobs must not be listed verbatim.
                #expect(message.contains("model-ops-0012") == false)
            } else {
                Issue.record("Expected missingRequired error, got \(error)")
            }
        }
    }

    @Test("lora publishes list surfaces a readable message when no publishes are recorded")
    func loraPublishesListRendersEmptyMessage() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: #"{"operation":"registry_snapshot","publishes":[]}"#
        ))
        let output = try await MelixCLIRunner(client: client).run(
            .loraPublishesList(.init(modelID: "melix-dev-text"))
        )
        #expect(output == "No publishes recorded.\n")
    }

    @Test("lora resume inherits hf dataset fields from the manifest when dataset_uri is absent")
    func loraResumeInheritsHFDatasetFields() async throws {
        let client = StubControlPlaneXPCClient()
        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-lora-resume-hf-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        let manifestURL = tempDir.appendingPathComponent("train_lora.adapter.json")
        try writeJSONObjectForTest(
            [
                "adapter_name": "nightly-qwen35",
                "dataset_source_kind": "hf_dataset",
                "hf_dataset_path": "HuggingFaceH4/ultrachat_200k",
                "hf_dataset_name": "default",
                "hf_train_split": "train_sft",
                "preset_id": "balanced_adapter",
            ],
            to: manifestURL
        )

        await client.setModelOperationResult(
            makeModelOperationResult(manifestJSON: makeExperimentsRegistryManifest(bestManifestPath: manifestURL.path)),
            forOperation: "registry_snapshot"
        )
        await client.setModelOperationResult(
            makeModelOperationResult(outputPath: "/tmp/resume-hf.adapter.json"),
            forOperation: "train_lora"
        )

        _ = try await MelixCLIRunner(client: client).run(
            .loraResume(.init(modelID: "melix-dev-text", groupID: "nightly-qwen35"))
        )

        let calls = await client.modelOperationCalls.filter { $0.ext["melix.registry_rescan"] != "true" }
        let trainCall = try #require(calls.last)
        #expect(trainCall.operation == "train_lora")
        #expect(trainCall.ext["dataset_source_kind"] == "hf_dataset")
        #expect(trainCall.ext["dataset_uri"] == "HuggingFaceH4/ultrachat_200k")
        #expect(trainCall.ext["hf_dataset_path"] == "HuggingFaceH4/ultrachat_200k")
        #expect(trainCall.ext["hf_dataset_name"] == "default")
        #expect(trainCall.ext["hf_train_split"] == "train_sft")
    }

    @Test("lora experiments show errors for an unknown group and lists known ids")
    func loraExperimentsShowErrorsForUnknownGroup() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: makeExperimentsRegistryManifest()
        ))

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .loraExperimentsShow(.init(modelID: "melix-dev-text", groupID: "missing"))
            )
            Issue.record("Expected experiments show to throw for an unknown group")
        } catch let error as MelixCLIError {
            if case .missingRequired(let message) = error {
                #expect(message.contains("missing"))
                #expect(message.contains("nightly-qwen35"))
            } else {
                Issue.record("Expected missingRequired error, got \(error)")
            }
        }
    }

    @Test("lora resume resolves the best adapter manifest and invokes train_lora")
    func loraResumeResolvesBestAdapterAndTrains() async throws {
        let client = StubControlPlaneXPCClient()
        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-lora-resume-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        let manifestURL = tempDir.appendingPathComponent("train_lora.adapter.json")
        try writeJSONObjectForTest(
            [
                "adapter_name": "nightly-qwen35",
                "dataset_uri": "/tmp/datasets/nightly.jsonl",
                "preset_id": "balanced_adapter",
                "experiment_group_id": "nightly-qwen35",
                "experiment_group_title": "Nightly Qwen35",
            ],
            to: manifestURL
        )

        await client.setModelOperationResult(
            makeModelOperationResult(manifestJSON: makeExperimentsRegistryManifest(bestManifestPath: manifestURL.path)),
            forOperation: "registry_snapshot"
        )
        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-train-lora/resume-out/train_lora.adapter.json",
                manifestJSON: #"{"operation":"train_lora","resume_manifest_path":"\#(manifestURL.path)"}"#
            ),
            forOperation: "train_lora"
        )

        let output = try await MelixCLIRunner(client: client).run(
            .loraResume(.init(modelID: "melix-dev-text", groupID: "nightly-qwen35"))
        )

        let calls = await client.modelOperationCalls.filter { $0.ext["melix.registry_rescan"] != "true" }
        #expect(calls.count == 2)
        #expect(calls.first?.operation == "registry_snapshot")
        let trainCall = try #require(calls.last)
        #expect(trainCall.operation == "train_lora")
        #expect(trainCall.ext["resume_manifest_path"] == manifestURL.path)
        #expect(trainCall.ext["dataset_uri"] == "/tmp/datasets/nightly.jsonl")
        #expect(trainCall.ext["adapter_name"] == "nightly-qwen35")
        #expect(trainCall.ext["preset_id"] == "balanced_adapter")
        #expect(trainCall.ext["experiment_group_id"] == "nightly-qwen35")
        #expect(output == "/tmp/melix-train-lora/resume-out/train_lora.adapter.json")
    }

    @Test("lora resume applies CLI overrides over manifest defaults")
    func loraResumeAppliesCLIOverrides() async throws {
        let client = StubControlPlaneXPCClient()
        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-lora-resume-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        let manifestURL = tempDir.appendingPathComponent("train_lora.adapter.json")
        try writeJSONObjectForTest(
            [
                "adapter_name": "nightly-qwen35",
                "dataset_uri": "/tmp/datasets/nightly.jsonl",
                "preset_id": "balanced_adapter",
            ],
            to: manifestURL
        )

        await client.setModelOperationResult(
            makeModelOperationResult(manifestJSON: makeExperimentsRegistryManifest(bestManifestPath: manifestURL.path)),
            forOperation: "registry_snapshot"
        )
        await client.setModelOperationResult(
            makeModelOperationResult(outputPath: "/tmp/resume.adapter.json"),
            forOperation: "train_lora"
        )

        _ = try await MelixCLIRunner(client: client).run(
            .loraResume(.init(
                modelID: "melix-dev-text",
                groupID: "nightly-qwen35",
                presetID: "quality_adapter",
                adapterName: "resumed-adapter",
                datasetURI: "/tmp/datasets/new.jsonl"
            ))
        )

        let calls = await client.modelOperationCalls
        let trainCall = try #require(calls.last)
        #expect(trainCall.ext["dataset_uri"] == "/tmp/datasets/new.jsonl")
        #expect(trainCall.ext["adapter_name"] == "resumed-adapter")
        #expect(trainCall.ext["preset_id"] == "quality_adapter")
    }

    @Test("lora resume surfaces error when the group has no recommended adapter")
    func loraResumeErrorsWhenGroupHasNoBestAdapter() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(
            makeModelOperationResult(manifestJSON: makeExperimentsRegistryManifest(bestManifestPath: "")),
            forOperation: "registry_snapshot"
        )

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .loraResume(.init(modelID: "melix-dev-text", groupID: "nightly-qwen35"))
            )
            Issue.record("Expected resume to throw when no best adapter exists")
        } catch let error as MelixCLIError {
            if case .missingRequired(let message) = error {
                #expect(message.contains("no recommended adapter"))
            } else {
                Issue.record("Expected missingRequired error, got \(error)")
            }
        }
    }

    @Test("lora resume surfaces a readable error when the manifest path is missing on disk")
    func loraResumeErrorsWhenManifestMissing() async throws {
        let client = StubControlPlaneXPCClient()
        let missingPath = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-missing-\(UUID().uuidString).json")
            .path
        await client.setModelOperationResult(
            makeModelOperationResult(manifestJSON: makeExperimentsRegistryManifest(bestManifestPath: missingPath)),
            forOperation: "registry_snapshot"
        )

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .loraResume(.init(modelID: "melix-dev-text", groupID: "nightly-qwen35"))
            )
            Issue.record("Expected resume to throw for a missing manifest")
        } catch let error as MelixCLIError {
            if case .runtime(let message) = error {
                #expect(message.contains(missingPath))
            } else {
                Issue.record("Expected runtime error, got \(error)")
            }
        }
    }

    @Test("lora train forwards dataset, adapter, repo, and tuning parameters")
    func loraTrainForwardsExpectedOperationPayload() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(outputPath: "/tmp/melix/train_lora/job-1"))

        let output = try await MelixCLIRunner(client: client).run(
            .loraTrain(
                .init(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    datasetSourceKind: "local_package",
                    datasetURI: "/tmp/datasets/alpaca.jsonl",
                    adapterName: "demo-adapter",
                    targetRepo: "melix/demo-adapter",
                    parameters: [
                        "preset_id": "balanced_adapter",
                        "experiment_group_id": "nightly-qwen35",
                        "rank": "8",
                        "epochs": "3",
                    ]
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(output == "/tmp/melix/train_lora/job-1")
        #expect(call.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(call.operation == "train_lora")
        #expect(call.ext["dataset_source_kind"] == "local_package")
        #expect(call.ext["dataset_uri"] == "/tmp/datasets/alpaca.jsonl")
        #expect(call.ext["adapter_name"] == "demo-adapter")
        #expect(call.ext["target_repo"] == "melix/demo-adapter")
        #expect(call.ext["preset_id"] == "balanced_adapter")
        #expect(call.ext["experiment_group_id"] == "nightly-qwen35")
        #expect(call.ext["rank"] == "8")
        #expect(call.ext["epochs"] == "3")
    }

    @Test("lora train forwards Hugging Face dataset metadata and boolean flags")
    func loraTrainForwardsHFDatasetPayload() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(outputPath: "/tmp/melix/train_lora/job-hf"))

        let output = try await MelixCLIRunner(client: client).run(
            .loraTrain(
                .init(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    datasetSourceKind: "hf_dataset",
                    datasetURI: "",
                    adapterName: "hf-demo-adapter",
                    trainingMode: "qlora",
                    parameters: [
                        "hf_dataset_path": "HuggingFaceH4/ultrachat_200k",
                        "hf_dataset_name": "default",
                        "hf_dataset_revision": "main",
                        "hf_train_split": "train_sft",
                        "hf_valid_split": "test_sft",
                        "sample_limit": "8",
                        "text_feature": "messages",
                        "response_only": "true",
                        "mask_prompt": "true",
                        "gradient_checkpointing": "true",
                        "derived_model_alias": "melix-qwen35-acceptance",
                    ]
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(output == "/tmp/melix/train_lora/job-hf")
        #expect(call.ext["dataset_source_kind"] == "hf_dataset")
        #expect(call.ext["dataset_uri"] == nil)
        #expect(call.ext["hf_dataset_path"] == "HuggingFaceH4/ultrachat_200k")
        #expect(call.ext["hf_dataset_name"] == "default")
        #expect(call.ext["hf_dataset_revision"] == "main")
        #expect(call.ext["hf_train_split"] == "train_sft")
        #expect(call.ext["hf_valid_split"] == "test_sft")
        #expect(call.ext["training_mode"] == "qlora")
        #expect(call.ext["sample_limit"] == "8")
        #expect(call.ext["text_feature"] == "messages")
        #expect(call.ext["response_only"] == "true")
        #expect(call.ext["mask_prompt"] == "true")
        #expect(call.ext["gradient_checkpointing"] == "true")
        #expect(call.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(call.ext["derived_model_alias"] == "melix-qwen35-acceptance")
    }

    @Test("lora train returns manifest json when requested")
    func loraTrainReturnsManifestJSONWhenRequested() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            outputPath: "/tmp/melix/train_lora/job-1",
            manifestJSON: #"{"job_id":"job-1","status":"completed"}"#
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraTrain(
                .init(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    datasetSourceKind: "local_package",
                    datasetURI: "/tmp/datasets/alpaca.jsonl",
                    adapterName: "demo-adapter",
                    json: true
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.ext["target_repo"] == nil)
        #expect(output == #"{"job_id":"job-1","status":"completed"}"#)
    }

    @Test("lora train memory fit preflight blocks unsafe Hub model targets")
    func loraTrainMemoryFitPreflightBlocksUnsafeHubModelTargets() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setHubModelCard(
            makeHubModelCard(
                repoID: "mlx-community/Qwen3.6-35B-A3B-4bit",
                localFitStatus: "blocked",
                localFitReasons: ["Estimated resident memory exceeds the safety threshold."],
                estimatedArtifactBytes: 24_000_000_000,
                estimatedResidentBytes: 48_000_000_000,
                recommendedAction: "Choose a smaller training base model."
            )
        )

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .loraTrain(
                    .init(
                        modelID: "mlx-community/Qwen3.6-35B-A3B-4bit",
                        datasetURI: "/tmp/datasets/alpaca.jsonl",
                        adapterName: "demo-adapter",
                        preflightFitCheck: true
                    )
                )
            )
            Issue.record("Expected memory fit preflight to block LoRA training.")
        } catch let error as MelixCLIError {
            guard case .runtime(let message) = error else {
                Issue.record("Expected runtime error.")
                return
            }
            #expect(message.contains("blocked training"))
            #expect(message.contains("fit_status=blocked"))
            #expect(message.contains("--allow-memory-risk"))
        }

        #expect(await client.lastModelOperationCall == nil)
    }

    @Test("lora train memory risk override stores fit receipt in operation ext")
    func loraTrainMemoryRiskOverrideStoresFitReceiptParameters() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setHubModelCard(
            makeHubModelCard(
                repoID: "mlx-community/Qwen3.6-35B-A3B-4bit",
                localFitStatus: "heavy",
                localFitReasons: ["Estimated resident memory exceeds the comfort budget."],
                estimatedArtifactBytes: 22_000_000_000,
                estimatedResidentBytes: 44_000_000_000,
                recommendedAction: "Train only on an idle high-memory Mac."
            )
        )
        await client.setModelOperationResult(makeModelOperationResult(outputPath: "/tmp/melix/train_lora/job-fit"))

        _ = try await MelixCLIRunner(client: client).run(
            .loraTrain(
                .init(
                    modelID: "mlx-community/Qwen3.6-35B-A3B-4bit",
                    datasetURI: "/tmp/datasets/alpaca.jsonl",
                    adapterName: "demo-adapter",
                    preflightFitCheck: true,
                    allowMemoryRisk: true
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)
        let receiptJSON = try #require(call.ext["memory_fit_receipt_json"])
        let receipt = try #require(parseJSONObject(receiptJSON))

        #expect(call.operation == "train_lora")
        #expect(call.ext["memory_fit_schema_version"] == "melix.memory_fit_receipt.v1")
        #expect(call.ext["memory_fit_target_kind"] == "train")
        #expect(call.ext["memory_fit_status"] == "heavy")
        #expect(call.ext["memory_fit_estimated_active_memory_bytes"] == "44000000000")
        #expect((UInt64(call.ext["memory_fit_available_disk_bytes"] ?? "") ?? 0) > 0)
        #expect(["good", "blocked", "unknown"].contains(call.ext["memory_fit_disk_status"] ?? ""))
        #expect((receipt["unknown_fields"] as? [String])?.contains("optimizer_state_bytes") == true)
        #expect((receipt["probe"] as? [String: Any])?["name"] as? String == "cli.memory_fit.train")
    }

    @Test("alignment train forwards algorithm and alignment-specific parameters")
    func alignmentTrainForwardsExpectedOperationPayload() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            outputPath: "/tmp/melix/train_lora/alignment-job",
            manifestJSON: #"{"schema_version":"melix.alignment_run.v1","job_id":"alignment-job"}"#
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .alignmentTrain(
                .init(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    datasetSourceKind: "local_package",
                    datasetURI: "/tmp/datasets/preference.jsonl",
                    adapterName: "aligned-adapter",
                    algorithm: "grpo",
                    parameters: [
                        "grpo_candidate_count": "4",
                        "candidate_generation_mode": "runtime_generate",
                        "candidate_scoring_mode": "reward_model",
                        "candidate_generation_max_tokens": "16",
                        "source_adapter_path": "/tmp/source/train_lora.adapter.json",
                        "reference_model_path": "/tmp/reference-model",
                        "reward_model_manifest_path": "/tmp/reward/manifest.json",
                    ],
                    json: true
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(output == #"{"schema_version":"melix.alignment_run.v1","job_id":"alignment-job"}"#)
        #expect(call.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(call.operation == "train_lora")
        #expect(call.ext["dataset_source_kind"] == "local_package")
        #expect(call.ext["dataset_uri"] == "/tmp/datasets/preference.jsonl")
        #expect(call.ext["adapter_name"] == "aligned-adapter")
        #expect(call.ext["training_mode"] == "grpo")
        #expect(call.ext["alignment_algorithm"] == "grpo")
        #expect(call.ext["grpo_candidate_count"] == "4")
        #expect(call.ext["candidate_generation_mode"] == "runtime_generate")
        #expect(call.ext["candidate_scoring_mode"] == "reward_model")
        #expect(call.ext["candidate_generation_max_tokens"] == "16")
        #expect(call.ext["source_adapter_path"] == "/tmp/source/train_lora.adapter.json")
        #expect(call.ext["reference_model_path"] == "/tmp/reference-model")
        #expect(call.ext["reward_model_manifest_path"] == "/tmp/reward/manifest.json")
    }

    @Test("lora dataset inspect forwards local source options and renders a dataset summary")
    func loraDatasetInspectForwardsExpectedOperationPayload() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            outputPath: "/tmp/melix/inspect/training_dataset.inspect.json",
            manifestJSON: #"""
            {
              "schema_version": "melix.training_dataset_inspection.v1",
              "dataset_id": "melix-alpaca-demo",
              "format": "prompt_completion",
              "sample_count": 2,
              "validation_sample_count": 1,
              "quality": {
                "duplicate_count": 1,
                "dirty_count": 1
              },
              "token_stats": {
                "prompt_tokens_p95": 8
              }
            }
            """#
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraDatasetInspect(
                .init(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    datasetSourceKind: "local_path",
                    datasetURI: "/tmp/datasets/alpaca.jsonl",
                    parameters: [
                        "template": "alpaca",
                        "validation_ratio": "0.2",
                        "preview_count": "4",
                    ]
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.operation == "build_training_dataset")
        #expect(call.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(call.ext["inspect_only"] == "true")
        #expect(call.ext["dataset_source_kind"] == "local_path")
        #expect(call.ext["dataset_uri"] == "/tmp/datasets/alpaca.jsonl")
        #expect(call.ext["template"] == "alpaca")
        #expect(call.ext["validation_ratio"] == "0.2")
        #expect(call.ext["preview_count"] == "4")
        #expect(output.contains("dataset_id=melix-alpaca-demo"))
        #expect(output.contains("format=prompt_completion"))
        #expect(output.contains("sample_count=2"))
        #expect(output.contains("duplicate_count=1"))
        #expect(output.contains("prompt_tokens_p95=8"))
    }

    @Test("lora dataset build forwards Hugging Face source metadata and returns the built package path")
    func loraDatasetBuildForwardsExpectedOperationPayload() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            outputPath: "/tmp/melix/built-dataset",
            manifestJSON: #"{"dataset_id":"melix-ultrachat-built","sample_count":8}"#
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraDatasetBuild(
                .init(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    datasetSourceKind: "hf_dataset",
                    datasetURI: "",
                    outputDir: "/tmp/melix/built-dataset",
                    parameters: [
                        "hf_dataset_path": "HuggingFaceH4/ultrachat_200k",
                        "hf_dataset_name": "default",
                        "hf_train_split": "train_sft",
                        "hf_valid_split": "test_sft",
                        "template": "chat_messages",
                        "dataset_id": "melix-ultrachat-built",
                    ]
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(output == "/tmp/melix/built-dataset")
        #expect(call.operation == "build_training_dataset")
        #expect(call.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(call.outputDir == "/tmp/melix/built-dataset")
        #expect(call.ext["inspect_only"] == nil)
        #expect(call.ext["dataset_source_kind"] == "hf_dataset")
        #expect(call.ext["hf_dataset_path"] == "HuggingFaceH4/ultrachat_200k")
        #expect(call.ext["hf_dataset_name"] == "default")
        #expect(call.ext["hf_train_split"] == "train_sft")
        #expect(call.ext["hf_valid_split"] == "test_sft")
        #expect(call.ext["template"] == "chat_messages")
        #expect(call.ext["dataset_id"] == "melix-ultrachat-built")
    }

    @Test("lora activate forwards adapter path and derived alias")
    func loraActivateForwardsExpectedOperationPayload() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(outputPath: "/tmp/melix/activate_adapter/job-2"))

        let output = try await MelixCLIRunner(client: client).run(
            .loraActivate(
                .init(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    adapterPath: "/tmp/melix/adapters/demo-adapter.json",
                    derivedModelAlias: "melix-qwen35-acceptance",
                    activationMode: "adapter_backed_runtime"
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(output == "/tmp/melix/activate_adapter/job-2")
        #expect(call.operation == "activate_adapter")
        #expect(call.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(call.ext["artifact_path"] == "/tmp/melix/adapters/demo-adapter.json")
        #expect(call.ext["derived_model_alias"] == "melix-qwen35-acceptance")
        #expect(call.ext["activation_mode"] == "adapter_backed_runtime")
    }

    @Test("lora activate returns manifest json when requested without an alias")
    func loraActivateReturnsManifestJSONWhenRequested() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            outputPath: "/tmp/melix/activate_adapter/job-2",
            manifestJSON: #"{"job_id":"job-2","status":"completed"}"#
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraActivate(
                .init(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    adapterPath: "/tmp/melix/adapters/demo-adapter.json",
                    json: true
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.ext["derived_model_alias"] == nil)
        #expect(output == #"{"job_id":"job-2","status":"completed"}"#)
    }

    @Test("lora remove-derived forwards the derived model target")
    func loraRemoveDerivedForwardsExpectedOperationPayload() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(outputPath: "/tmp/melix/remove_derived_model/job-3"))

        let output = try await MelixCLIRunner(client: client).run(
            .loraRemoveDerived(
                .init(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    derivedModelID: "melix-qwen35-acceptance"
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(output == "/tmp/melix/remove_derived_model/job-3")
        #expect(call.operation == "remove_derived_model")
        #expect(call.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(call.ext["derived_model_id"] == "melix-qwen35-acceptance")
        #expect(call.ext["manifest_path"] == nil)
    }

    @Test("lora remove-derived forwards the manifest path target")
    func loraRemoveDerivedForwardsManifestPathPayload() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(outputPath: "/tmp/melix/remove_derived_model/job-4"))

        let output = try await MelixCLIRunner(client: client).run(
            .loraRemoveDerived(
                .init(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    manifestPath: "/tmp/melix/activate_adapter/job-2/activate_adapter.derived_model.json"
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(output == "/tmp/melix/remove_derived_model/job-4")
        #expect(call.operation == "remove_derived_model")
        #expect(call.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(call.ext["derived_model_id"] == nil)
        #expect(call.ext["manifest_path"] == "/tmp/melix/activate_adapter/job-2/activate_adapter.derived_model.json")
    }

    @Test("lora publish forwards adapter and merged export selections")
    func loraPublishForwardsExplicitExportSelections() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(outputPath: "/tmp/melix/upload/job-5"))

        let adapterOutput = try await MelixCLIRunner(client: client).run(
            .loraPublish(
                .init(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    targetRepo: "melix/adapters/demo",
                    exportKind: .adapterExport,
                    artifactPath: "/tmp/melix/train_lora.adapter.json",
                    artifactManifestPath: "/tmp/melix/train_lora.adapter.json"
                )
            )
        )
        let adapterCall = try #require(await client.lastModelOperationCall)

        #expect(adapterOutput == "/tmp/melix/upload/job-5")
        #expect(adapterCall.operation == "upload")
        #expect(adapterCall.ext["target_repo"] == "melix/adapters/demo")
        #expect(adapterCall.ext["artifact_kind"] == "adapter_export")
        #expect(adapterCall.ext["artifact_path"] == "/tmp/melix/train_lora.adapter.json")
        #expect(adapterCall.ext["artifact_manifest_path"] == "/tmp/melix/train_lora.adapter.json")

        await client.setModelOperationResult(makeModelOperationResult(
            outputPath: "/tmp/melix/upload/job-6",
            manifestJSON: #"{"job_id":"job-6","operation":"upload"}"#
        ))
        let mergedOutput = try await MelixCLIRunner(client: client).run(
            .loraPublish(
                .init(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    targetRepo: "melix/models/demo-merged",
                    exportKind: .mergedExport,
                    artifactPath: "/tmp/melix/activate_adapter/job-2/manifest.json",
                    artifactManifestPath: "/tmp/melix/activate_adapter/job-2/manifest.json",
                    json: true
                )
            )
        )
        let mergedCall = try #require(await client.lastModelOperationCall)

        #expect(mergedOutput.contains("job-6"))
        #expect(mergedCall.ext["target_repo"] == "melix/models/demo-merged")
        #expect(mergedCall.ext["artifact_kind"] == "merged_export")
        #expect(mergedCall.ext["artifact_path"] == "/tmp/melix/activate_adapter/job-2/manifest.json")
        #expect(mergedCall.ext["artifact_manifest_path"] == "/tmp/melix/activate_adapter/job-2/manifest.json")
    }

    @Test("lora publish infers adapter export from the manifest schema at runtime")
    func loraPublishInfersAdapterExportFromManifest() async throws {
        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-publish-adapter-infer-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        let manifestURL = tempDir.appendingPathComponent("train_lora.adapter.json")
        try writeJSONObjectForTest(
            [
                "schema_version": "melix.lora_adapter_package.v1",
                "artifact_kind": "adapter",
                "adapter_name": "demo",
            ],
            to: manifestURL
        )

        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(outputPath: "/tmp/melix/upload/inferred-adapter"))

        _ = try await MelixCLIRunner(client: client).run(
            .loraPublish(
                .init(
                    modelID: "melix-dev-text",
                    targetRepo: "melix/adapters/demo",
                    exportKind: nil,
                    artifactPath: manifestURL.path,
                    artifactManifestPath: manifestURL.path
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)
        #expect(call.ext["artifact_kind"] == "adapter_export")
    }

    @Test("lora publish infers merged export from a fused derived-model manifest at runtime")
    func loraPublishInfersMergedExportFromManifest() async throws {
        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-publish-merged-infer-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        let manifestURL = tempDir.appendingPathComponent("manifest.json")
        try writeJSONObjectForTest(
            [
                "schema_version": "melix.derived_text_model.v1",
                "activation_mode": "fused_derived_model",
            ],
            to: manifestURL
        )

        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(outputPath: "/tmp/melix/upload/inferred-merged"))

        _ = try await MelixCLIRunner(client: client).run(
            .loraPublish(
                .init(
                    modelID: "melix-dev-text",
                    targetRepo: "melix/models/demo",
                    exportKind: nil,
                    artifactPath: manifestURL.path,
                    artifactManifestPath: manifestURL.path
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)
        #expect(call.ext["artifact_kind"] == "merged_export")
    }

    @Test("lora publish rejects an explicit --export-kind that contradicts the manifest content")
    func loraPublishRejectsExportKindMismatchAgainstManifest() async throws {
        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-publish-mismatch-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        let manifestURL = tempDir.appendingPathComponent("train_lora.adapter.json")
        try writeJSONObjectForTest(
            [
                "schema_version": "melix.lora_adapter_package.v1",
                "artifact_kind": "adapter",
            ],
            to: manifestURL
        )

        let client = StubControlPlaneXPCClient()

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .loraPublish(
                    .init(
                        modelID: "melix-dev-text",
                        targetRepo: "melix/models/demo",
                        exportKind: .mergedExport,
                        artifactPath: manifestURL.path,
                        artifactManifestPath: manifestURL.path
                    )
                )
            )
            Issue.record("Expected publish to reject mismatched --export-kind vs manifest")
        } catch let error as MelixCLIError {
            if case .usage(let message) = error {
                #expect(message.contains("--export-kind merged"))
                #expect(message.contains("adapter"))
            } else {
                Issue.record("Expected .usage error, got \(error)")
            }
        }
        #expect(await client.lastModelOperationCall == nil)
    }

    @Test("lora publish errors when the manifest cannot be inferred and --export-kind is absent")
    func loraPublishErrorsOnAmbiguousManifestWithoutExportKind() async throws {
        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-publish-ambiguous-runner-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        let manifestURL = tempDir.appendingPathComponent("unknown.json")
        try "{}".write(to: manifestURL, atomically: true, encoding: .utf8)

        let client = StubControlPlaneXPCClient()

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .loraPublish(
                    .init(
                        modelID: "melix-dev-text",
                        targetRepo: "melix/models/demo",
                        exportKind: nil,
                        artifactPath: manifestURL.path,
                        artifactManifestPath: manifestURL.path
                    )
                )
            )
            Issue.record("Expected publish to reject ambiguous manifest without --export-kind")
        } catch let error as MelixCLIError {
            if case .usage(let message) = error {
                #expect(message.contains("--export-kind"))
            } else {
                Issue.record("Expected .usage error, got \(error)")
            }
        }
        #expect(await client.lastModelOperationCall == nil)
    }

    @Test("lora publish honors explicit --export-kind when the manifest file is unreadable")
    func loraPublishHonorsExplicitKindWhenManifestUnreadable() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(outputPath: "/tmp/melix/upload/escape-hatch"))

        // Path intentionally does not exist on disk — the explicit override is the escape hatch.
        let missingPath = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-missing-\(UUID().uuidString).json").path

        _ = try await MelixCLIRunner(client: client).run(
            .loraPublish(
                .init(
                    modelID: "melix-dev-text",
                    targetRepo: "melix/adapters/demo",
                    exportKind: .adapterExport,
                    artifactPath: missingPath,
                    artifactManifestPath: missingPath
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)
        #expect(call.ext["artifact_kind"] == "adapter_export")
    }

    @Test("subprocess-backed lora operations build public melix arguments and decode manifest payloads")
    func subprocessBackedLoraOperationsBuildPublicCLIArguments() async throws {
        let client = StubControlPlaneXPCClient()
        let executor = RecordingCLICommandExecutor(
            responses: [
                #"{"operation":"train_lora","job_id":"train-job-1","output_path":"/tmp/melix/train_lora/job-1","adapter_name":"demo-adapter"}"#,
                #"{"operation":"activate_adapter","job_id":"activate-job-1","output_path":"/tmp/melix/activate_adapter/job-1","derived_model_id":"melix-qwen35-acceptance"}"#,
                #"{"operation":"registry_snapshot","adapters":[{"adapter_name":"demo-adapter","status":"activated"}]}"#,
            ]
        )
        let runner = MelixCLIRunner(
            client: client,
            commandExecutor: executor.run
        )

        let trainResult = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "train_lora",
            outputDir: "",
            ext: [
                "dataset_source_kind": "hf_dataset",
                "adapter_name": "demo-adapter",
                "training_mode": "qlora",
                "preset_id": "debug_fast",
                "experiment_group_id": "phase8-real-small-model",
                "max_steps": "2",
                "hf_dataset_path": "HuggingFaceH4/ultrachat_200k",
                "hf_train_split": "train_sft",
                "chat_feature": "messages",
                "derived_model_alias": "melix-qwen35-acceptance",
            ]
        )
        let activateResult = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "activate_adapter",
            outputDir: "",
            ext: [
                "artifact_path": "/tmp/melix/train_lora/job-1/train_lora.adapter.json",
                "activation_mode": "adapter_backed_runtime",
                "derived_model_alias": "melix-qwen35-acceptance",
            ]
        )
        let registrySnapshot = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "registry_snapshot",
            outputDir: "",
            ext: [:]
        )
        let commands = await executor.commands

        #expect(await client.lastModelOperationCall == nil)
        #expect(trainResult.outputPath == "/tmp/melix/train_lora/job-1")
        #expect(activateResult.outputPath == "/tmp/melix/activate_adapter/job-1")
        #expect(parseJSONObject(registrySnapshot.manifestJson)?["operation"] as? String == "registry_snapshot")
        #expect(commands.count == 3)
        #expect(commands[0].contains("lora"))
        #expect(commands[0].contains("train"))
        #expect(commands[0].contains("--training-mode"))
        #expect(commands[0].contains("qlora"))
        #expect(commands[0].contains("--preset"))
        #expect(commands[0].contains("debug_fast"))
        #expect(commands[0].contains("--experiment-group"))
        #expect(commands[0].contains("phase8-real-small-model"))
        #expect(commands[0].contains("--max-steps"))
        #expect(commands[0].contains("2"))
        #expect(commands[0].contains("--hf-dataset-path"))
        #expect(commands[0].contains("HuggingFaceH4/ultrachat_200k"))
        #expect(commands[1].contains("activate"))
        #expect(commands[1].contains("--activation-mode"))
        #expect(commands[1].contains("adapter_backed_runtime"))
        #expect(commands[2] == ["lora", "list", "--model-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit", "--json"])
    }

    @Test("subprocess-backed dataset operations build public melix arguments")
    func subprocessBackedDatasetOperationsBuildPublicCLIArguments() async throws {
        let client = StubControlPlaneXPCClient()
        let executor = RecordingCLICommandExecutor(
            responses: [
                #"{"operation":"dataset_snapshot","dataset_registry":{"datasets":[],"roots":[]}}"#,
                #"{"operation":"dataset_download","repo_id":"org/dataset","revision":"main","snapshot_path":"/tmp/hf-cache/datasets--org--dataset/snapshots/abc123"}"#,
                #"{"operation":"dataset_remove","repo_id":"org/dataset","revision":"main","snapshot_id":"abc123","removed_snapshot_path":"/tmp/hf-cache/datasets--org--dataset/snapshots/abc123"}"#,
            ]
        )
        let runner = MelixCLIRunner(
            client: client,
            commandExecutor: executor.run
        )

        let snapshotResult = try await runner.performModelOperation(
            modelID: "melix-datasets",
            operation: "dataset_snapshot",
            outputDir: "",
            ext: [:]
        )
        let downloadResult = try await runner.performModelOperation(
            modelID: "org/dataset",
            operation: "dataset_download",
            outputDir: "",
            ext: [
                "melix.hf_revision": "main",
                "melix.hf_token": "hf_secret",
            ]
        )
        let removeResult = try await runner.performModelOperation(
            modelID: "org/dataset",
            operation: "dataset_remove",
            outputDir: "",
            ext: [
                "melix.hf_revision": "main",
                "melix.hf_snapshot_id": "abc123",
            ]
        )
        let commands = await executor.commands

        #expect(await client.lastModelOperationCall == nil)
        #expect(parseJSONObject(snapshotResult.manifestJson)?["operation"] as? String == "dataset_snapshot")
        #expect(downloadResult.outputPath == "/tmp/hf-cache/datasets--org--dataset/snapshots/abc123")
        #expect(parseJSONObject(removeResult.manifestJson)?["operation"] as? String == "dataset_remove")
        #expect(commands[0] == ["dataset", "list", "--json"])
        #expect(commands[1] == ["dataset", "hub", "download", "--repo-id", "org/dataset", "--revision", "main", "--hf-token", "hf_secret", "--json"])
        #expect(commands[2] == ["dataset", "remove", "--repo-id", "org/dataset", "--revision", "main", "--snapshot-id", "abc123", "--json"])
    }

    @Test("subprocess-backed legacy alignment training mode uses alignment train")
    func subprocessBackedLegacyAlignmentTrainingModeUsesAlignmentTrain() async throws {
        let client = StubControlPlaneXPCClient()
        let executor = RecordingCLICommandExecutor(
            responses: [
                #"{"operation":"train_alignment","job_id":"alignment-job-1","output_path":"/tmp/melix/train_lora/alignment-job-1","adapter_name":"demo-grpo-adapter"}"#,
            ]
        )
        let runner = MelixCLIRunner(
            client: client,
            commandExecutor: executor.run
        )

        _ = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "train_lora",
            outputDir: "",
            ext: [
                "dataset_source_kind": "local_package",
                "dataset_uri": "/tmp/datasets/prompt-candidate",
                "adapter_name": "demo-grpo-adapter",
                "training_mode": "grpo",
                "max_steps": "3",
                "sample_limit": "8",
                "gradient_accumulation": "4",
                "grpo_candidate_count": "4",
                "source_adapter_path": "/tmp/source/train_lora.adapter.json",
            ]
        )

        let commands = await executor.commands
        #expect(commands.count == 1)
        #expect(Array(commands[0].prefix(2)) == ["alignment", "train"])
        #expect(commands[0].contains("--algorithm"))
        #expect(commands[0].contains("grpo"))
        #expect(commands[0].contains("--max-steps"))
        #expect(commands[0].contains("3"))
        #expect(commands[0].contains("--sample-limit"))
        #expect(commands[0].contains("8"))
        #expect(commands[0].contains("--gradient-accumulation"))
        #expect(commands[0].contains("4"))
        #expect(commands[0].contains("--source-adapter-path"))
        #expect(commands[0].contains("/tmp/source/train_lora.adapter.json"))
    }

    @Test("subprocess-backed lora publish builds explicit adapter and merged publish arguments")
    func subprocessBackedLoraPublishBuildsExplicitArguments() async throws {
        let client = StubControlPlaneXPCClient()
        let executor = RecordingCLICommandExecutor(
            responses: [
                #"{"operation":"upload","job_id":"upload-adapter-1","output_path":"/tmp/melix/upload/adapter"}"#,
                #"{"operation":"upload","job_id":"upload-merged-1","output_path":"/tmp/melix/upload/merged"}"#,
            ]
        )
        let runner = MelixCLIRunner(client: client, commandExecutor: executor.run)

        _ = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "upload",
            outputDir: "",
            ext: [
                "target_repo": "melix/adapters/demo",
                "artifact_path": "/tmp/melix/train_lora.adapter.json",
                "artifact_kind": "adapter_export",
                "artifact_manifest_path": "/tmp/melix/train_lora.adapter.json",
            ]
        )
        _ = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "upload",
            outputDir: "",
            ext: [
                "target_repo": "melix/models/demo-merged",
                "artifact_path": "/tmp/melix/activate_adapter/manifest.json",
                "artifact_kind": "merged_export",
                "artifact_manifest_path": "/tmp/melix/activate_adapter/manifest.json",
            ]
        )
        let commands = await executor.commands

        #expect(commands.count == 2)
        #expect(commands[0].starts(with: ["lora", "publish", "--model-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"]))
        #expect(commands[0].contains("--adapter-path"))
        #expect(commands[0].contains("/tmp/melix/train_lora.adapter.json"))
        #expect(commands[1].contains("--manifest-path"))
        #expect(commands[1].contains("/tmp/melix/activate_adapter/manifest.json"))
        #expect(commands[1].contains("melix/models/demo-merged"))
    }

    @Test("subprocess-backed evaluation compare builds public melix compare arguments")
    func subprocessBackedEvaluationCompareBuildsPublicCLIArguments() async throws {
        let client = StubControlPlaneXPCClient()
        let executor = RecordingCLICommandExecutor(
            responses: [
                """
                [
                  {
                    "job_id": "eval-compare-1",
                    "model_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    "task_kind": "text-generation",
                    "source_repo": "",
                    "suite_id": "mmlu",
                    "dataset_id": "mmlu.dev.v1",
                    "sample_size": 6,
                    "scoring_mode": "multiple_choice_accuracy",
                    "status": "completed",
                    "output_dir": "/tmp/melix/evaluation/runs/eval-compare-1",
                    "created_at_unix_ms": 1712000000000,
                    "updated_at_unix_ms": 1712000001000,
                    "results": []
                  }
                ]
                """
            ]
        )
        let runner = MelixCLIRunner(
            client: client,
            commandExecutor: executor.run
        )

        let results = try await runner.runEvaluationCompare(
            EvalCompareOptions(
                modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                targetModelIDs: ["melix-qwen35-acceptance", "melix-qwen35-safety"],
                suites: ["mmlu"],
                sampleSize: 6,
                parameters: [
                    "batch_factor": "2",
                    "few_shot": "1",
                    "hints_path": "/tmp/melix/eval/math-hints.md",
                    "schema_path": "/tmp/melix/eval/result.schema.json",
                    "seed": "9",
                    "scoring_mode": "multiple_choice_accuracy",
                    "code_exec_policy": "sandboxed",
                ]
            )
        )
        let command = try #require(await executor.commands.last)

        #expect(results.count == 1)
        #expect(await client.evaluationRequests.isEmpty)
        #expect(await client.loadedModelIDs.isEmpty)
        #expect(command.starts(with: ["eval", "compare"]))
        #expect(command.contains("--target-model-id"))
        #expect(command.contains("melix-qwen35-acceptance"))
        #expect(command.contains("melix-qwen35-safety"))
        #expect(command.contains("--batch-factor"))
        #expect(command.contains("2"))
        #expect(command.contains("--few-shot"))
        #expect(command.contains("--schema"))
        #expect(command.contains("/tmp/melix/eval/result.schema.json"))
        #expect(command.contains("--hints"))
        #expect(command.contains("/tmp/melix/eval/math-hints.md"))
        #expect(command.contains("--seed"))
        #expect(command.contains("--scoring-mode"))
        #expect(command.contains("--code-exec-policy"))
        #expect(command.last == "--json")
    }

    @Test("eval compare forwards --target-adapter manifest paths to the subprocess argv")
    func evalCompareForwardsAdapterTargetsToSubprocessArgv() async throws {
        // Module 2 surface: when adapter-manifest targets are supplied via
        // --target-adapter, the subprocess argv echoes each repeatable flag
        // so the in-process worker can parse them into
        // compare_target_adapter_manifest_paths.
        let client = StubControlPlaneXPCClient()
        let executor = RecordingCLICommandExecutor(
            responses: [
                """
                [
                  {
                    "job_id": "eval-compare-adapter",
                    "model_id": "melix-dev-text",
                    "task_kind": "text-generation",
                    "source_repo": "",
                    "suite_id": "mmlu",
                    "dataset_id": "",
                    "sample_size": 2,
                    "scoring_mode": "multiple_choice_accuracy",
                    "status": "completed",
                    "output_dir": "/tmp/melix/evaluation/runs/eval-compare-adapter",
                    "created_at_unix_ms": 1712000000000,
                    "updated_at_unix_ms": 1712000001000,
                    "results": []
                  }
                ]
                """
            ]
        )
        let runner = MelixCLIRunner(
            client: client,
            commandExecutor: executor.run
        )

        let results = try await runner.runEvaluationCompare(
            EvalCompareOptions(
                modelID: "melix-dev-text",
                targetAdapterManifestPaths: [
                    "/tmp/melix-adapters/alpha.adapter.json",
                    "/tmp/melix-adapters/beta.adapter.json",
                ],
                suites: ["mmlu"],
                sampleSize: 2
            )
        )
        let command = try #require(await executor.commands.last)

        #expect(results.count == 1)
        // Ephemeral adapter targets should NOT trigger a pre-load on the
        // client — the worker materializes them during the compare run.
        #expect(await client.loadedModelIDs.isEmpty)
        // --target-adapter must appear twice, once per manifest path.
        let adapterFlagIndices = command.enumerated().compactMap { index, value in
            value == "--target-adapter" ? index : nil
        }
        #expect(adapterFlagIndices.count == 2)
        #expect(command.contains("/tmp/melix-adapters/alpha.adapter.json"))
        #expect(command.contains("/tmp/melix-adapters/beta.adapter.json"))
        // No registered-model targets were requested, so --target-model-id
        // must be absent.
        #expect(!command.contains("--target-model-id"))
    }

    @Test("process executor runs the configured subprocess with working-directory and environment overrides")
    func processExecutorRunsConfiguredSubprocess() async throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-cli-process-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let executor = MelixCLIProcessExecutor(
            baseCommand: [
                "/bin/zsh",
                "-lc",
                #"printf "%s" "$MELIX_SUBPROCESS_TEST:$PWD:$1""#,
                "melix-process",
            ],
            environment: ["MELIX_SUBPROCESS_TEST": "configured"],
            workingDirectory: root.path
        )

        let output = try await executor.run(arguments: ["runner-arg"])
        let detailed = try await executor.runDetailed(arguments: ["runner-arg"])
        let components = output.split(separator: ":", maxSplits: 2).map(String.init)

        #expect(components.count == 3)
        #expect(components[0] == "configured")
        #expect(
            URL(fileURLWithPath: components[1]).resolvingSymlinksInPath().path ==
            root.resolvingSymlinksInPath().path
        )
        #expect(components[2] == "runner-arg")
        #expect(detailed.exitCode == 0)
        #expect(detailed.stderr == "")
        #expect(detailed.stdout.trimmingCharacters(in: .whitespacesAndNewlines) == output)
    }

    @Test("process executor surfaces subprocess failures and rejects empty commands")
    func processExecutorSurfacesFailuresAndMisconfiguration() async throws {
        let failingExecutor = MelixCLIProcessExecutor(
            baseCommand: [
                "/bin/zsh",
                "-lc",
                #"printf "%s" "subprocess boom" >&2; exit 3"#,
                "melix-process",
            ]
        )

        do {
            _ = try await failingExecutor.run(arguments: [])
            Issue.record("Expected the configured subprocess to fail.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("subprocess boom"))
        }
        let failedDetails = try await failingExecutor.runDetailed(arguments: [])
        #expect(failedDetails.exitCode == 3)
        #expect(failedDetails.stderr == "subprocess boom")

        let misconfiguredExecutor = MelixCLIProcessExecutor(baseCommand: [])

        do {
            _ = try await misconfiguredExecutor.run(arguments: [])
            Issue.record("Expected an empty subprocess command to fail.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("The melix subprocess command is not configured."))
        }
    }

    @Test("subprocess-backed model operations cover local-package remove-derived and download argument branches")
    func subprocessBackedModelOperationsCoverAdditionalArgumentBranches() async throws {
        let client = StubControlPlaneXPCClient()
        let executor = RecordingCLICommandExecutor(
            responses: [
                #"{"operation":"train_lora","job_id":"train-local-1","output_path":"/tmp/melix/train_lora/train-local-1"}"#,
                #"{"operation":"remove_derived_model","job_id":"remove-job-1","output_path":"/tmp/melix/remove_derived_model/remove-job-1"}"#,
                #"{"operation":"download","job_id":"download-job-1","output_path":"/tmp/melix-downloads/qwen35"}"#,
            ]
        )
        let runner = MelixCLIRunner(client: client, commandExecutor: executor.run)

        let trainResult = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "train_lora",
            outputDir: "",
            ext: [
                "dataset_source_kind": "local_package",
                "dataset_uri": "/tmp/melix/datasets/alpaca",
                "adapter_name": "demo-adapter",
                "target_repo": "melix/demo-adapter",
                "response_only": "true",
                "mask_prompt": "true",
                "gradient_checkpointing": "true",
            ]
        )
        let removeResult = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "remove_derived_model",
            outputDir: "",
            ext: [
                "derived_model_id": "melix-qwen35-acceptance",
                "manifest_path": "/tmp/melix/activate_adapter/job-1/activate_adapter.derived_model.json",
            ]
        )
        let downloadResult = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "download",
            outputDir: "/tmp/melix-downloads",
            ext: [:]
        )
        let commands = await executor.commands

        #expect(trainResult.jobID == "train-local-1")
        #expect(removeResult.jobID == "remove-job-1")
        #expect(downloadResult.outputPath == "/tmp/melix-downloads/qwen35")
        #expect(commands.count == 3)
        #expect(commands[0].contains("--dataset-uri"))
        #expect(commands[0].contains("/tmp/melix/datasets/alpaca"))
        #expect(commands[0].contains("--response-only"))
        #expect(commands[0].contains("--mask-prompt"))
        #expect(commands[0].contains("--gradient-checkpointing"))
        #expect(commands[1].contains("remove-derived"))
        #expect(commands[1].contains("--derived-model-id"))
        #expect(commands[1].contains("--manifest-path"))
        #expect(commands[2].contains("download"))
        #expect(commands[2].contains("--output-dir"))
        #expect(commands[2].contains("/tmp/melix-downloads"))
    }

    @Test("subprocess-backed model operations cover convert quantize and upload argument branches")
    func subprocessBackedModelOperationsCoverPublicModelOpsBranches() async throws {
        let client = StubControlPlaneXPCClient()
        let executor = RecordingCLICommandExecutor(
            responses: [
                #"{"operation":"convert","job_id":"convert-job-1","output_path":"/tmp/melix-convert/convert.artifact"}"#,
                #"{"operation":"quantize","job_id":"quantize-job-1","output_path":"/tmp/melix-quantize/quantize.artifact"}"#,
                #"{"operation":"upload","job_id":"upload-job-1","output_path":"/tmp/melix-upload/upload.receipt.json"}"#,
            ]
        )
        let runner = MelixCLIRunner(client: client, commandExecutor: executor.run)

        let convertResult = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "convert",
            outputDir: "/tmp/melix-convert",
            ext: ["target_format": "melix_model_bundle"]
        )
        let quantizeResult = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "quantize",
            outputDir: "/tmp/melix-quantize",
            quantProfileID: "q4",
            weightQuant: "q4",
            kvQuant: "q8",
            ext: [
                "quantization_mode": "qat",
                "source_artifact_kind": "merged_adapter",
                "source_artifact_path": "/tmp/melix-export/merged",
                "quantization_backend": "mlx_lm_convert",
                "mlx_lm_q_bits": "4",
                "mlx_lm_q_group_size": "128",
                "mlx_lm_q_mode": "affine",
                "calibration_dataset_uri": "/tmp/melix-datasets/calibration",
                "quality_delta": "-0.01",
                "latency_delta": "-0.15",
            ]
        )
        let uploadResult = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "upload",
            outputDir: "/tmp/melix-upload",
            ext: [
                "target_repo": "melix/models/demo",
                "artifact_path": "/tmp/melix-convert/convert.artifact",
                "artifact_kind": "converted_model_bundle",
                "artifact_manifest_path": "/tmp/melix-convert/convert.artifact/manifest.json",
            ]
        )
        let commands = await executor.commands

        #expect(convertResult.jobID == "convert-job-1")
        #expect(quantizeResult.jobID == "quantize-job-1")
        #expect(uploadResult.jobID == "upload-job-1")
        #expect(commands.count == 3)
        #expect(commands[0].starts(with: ["convert", "--model-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"]))
        #expect(commands[0].contains("--output-dir"))
        #expect(commands[0].contains("/tmp/melix-convert"))
        #expect(commands[0].contains("--target-format"))
        #expect(commands[1].starts(with: ["quantize", "--model-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"]))
        #expect(commands[1].contains("--quant-profile-id"))
        #expect(commands[1].contains("--weight-quant"))
        #expect(commands[1].contains("--kv-quant"))
        #expect(commands[1].contains("--quantization-mode"))
        #expect(commands[1].contains("qat"))
        #expect(commands[1].contains("--source-artifact-kind"))
        #expect(commands[1].contains("merged_adapter"))
        #expect(commands[1].contains("--source-artifact-path"))
        #expect(commands[1].contains("/tmp/melix-export/merged"))
        #expect(commands[1].contains("--quantization-backend"))
        #expect(commands[1].contains("mlx_lm_convert"))
        #expect(commands[1].contains("--mlx-lm-q-bits"))
        #expect(commands[1].contains("4"))
        #expect(commands[1].contains("--mlx-lm-q-group-size"))
        #expect(commands[1].contains("128"))
        #expect(commands[1].contains("--mlx-lm-q-mode"))
        #expect(commands[1].contains("affine"))
        #expect(commands[1].contains("--calibration-dataset-uri"))
        #expect(commands[1].contains("/tmp/melix-datasets/calibration"))
        #expect(commands[1].contains("--quality-delta"))
        #expect(commands[1].contains("-0.01"))
        #expect(commands[1].contains("--latency-delta"))
        #expect(commands[1].contains("-0.15"))
        #expect(commands[2].starts(with: ["upload", "--model-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"]))
        #expect(commands[2].contains("--target-repo"))
        #expect(commands[2].contains("--artifact-path"))
        #expect(commands[2].contains("--artifact-kind"))
        #expect(commands[2].contains("--artifact-manifest-path"))
    }

    @Test("subprocess-backed model operations preserve raw manifest output when JSON decoding is unavailable")
    func subprocessBackedModelOperationsPreserveRawManifestOutput() async throws {
        let client = StubControlPlaneXPCClient()
        let executor = RecordingCLICommandExecutor(responses: ["plain-manifest-output"])
        let runner = MelixCLIRunner(client: client, commandExecutor: executor.run)

        let result = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "activate_adapter",
            outputDir: "",
            ext: [
                "artifact_path": "/tmp/melix/train_lora/job-1/train_lora.adapter.json",
            ]
        )

        #expect(result.operation == "activate_adapter")
        #expect(result.manifestJson == "plain-manifest-output")
        #expect(result.jobID.isEmpty)
        #expect(result.outputPath.isEmpty)
    }

    @Test("subprocess-backed eval compare supports repo ids and decodes nested result payloads")
    func subprocessBackedEvaluationCompareSupportsRepoTargetsAndNestedResults() async throws {
        let client = StubControlPlaneXPCClient()
        let executor = RecordingCLICommandExecutor(
            responses: [
                """
                [
                  0,
                  {
                    "job": {
                      "job_id": "eval-compare-2",
                      "model_id": "",
                      "task_kind": "text-generation",
                      "source_repo": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                      "suite_id": "mmlu",
                      "dataset_id": "mmlu.dev.v1",
                      "sample_size": 6,
                      "scoring_mode": "multiple_choice_accuracy",
                      "parameters": {
                        "batch_factor": "2"
                      },
                      "status": "completed",
                      "output_dir": "/tmp/melix/evaluation/runs/eval-compare-2",
                      "created_at_unix_ms": 1712000000000,
                      "updated_at_unix_ms": 1712000001000
                    },
                    "results": [
                      {
                        "job_id": "eval-compare-2",
                        "suite_id": "mmlu:melix-qwen35-acceptance",
                        "dataset_id": "mmlu.dev.v1",
                        "sample_size": 6,
                        "report_path": "/tmp/melix/evaluation/runs/eval-compare-2/summary.json",
                        "metrics": [
                          {
                            "name": "eval.compare.win_rate",
                            "value": 0.625,
                            "unit": "ratio"
                          }
                        ]
                      }
                    ]
                  }
                ]
                """
            ]
        )
        let runner = MelixCLIRunner(client: client, commandExecutor: executor.run)

        let results = try await runner.runEvaluationCompare(
            EvalCompareOptions(
                hfRepoID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                targetModelIDs: ["melix-qwen35-acceptance"],
                suites: ["mmlu"],
                sampleSize: 6,
                source: .localJSONL(path: "/tmp/eval/mmlu.jsonl"),
                fieldMapping: .init(
                    inputTextPath: "prompt",
                    targetPath: "expected",
                    sampleIDPath: "sample_id"
                ),
                profile: .init(
                    profileType: "final_result",
                    resultKind: "text",
                    extractionMode: "heuristic_final",
                    scoringMode: "multiple_choice_accuracy",
                    threshold: 0.8,
                    ignoredPaths: ["metadata.trace_id"]
                ),
                parameters: [
                        "batch_factor": "2",
                    "dataset_root": "/tmp/mmlu-split-01",
                    "few_shot": "1",
                    "seed": "9",
                    "scoring_mode": "multiple_choice_accuracy",
                    "code_exec_policy": "sandboxed",
                ]
            )
        )
        let command = try #require(await executor.commands.last)
        let first = try #require(results.first)
        let firstMetric = try #require(first.results.first?.metrics.first)

        #expect(await client.evaluationRequests.isEmpty)
        #expect(command.contains("--repo-id"))
        #expect(command.contains("mlx-community/Qwen3.5-0.8B-OptiQ-4bit"))
        #expect(command.contains("--target-model-id"))
        #expect(command.contains("melix-qwen35-acceptance"))
        #expect(command.contains("--source-jsonl"))
        #expect(command.contains("/tmp/eval/mmlu.jsonl"))
        #expect(command.contains("--field-input-text-path"))
        #expect(command.contains("prompt"))
        #expect(command.contains("--field-target-path"))
        #expect(command.contains("expected"))
        #expect(command.contains("--threshold"))
        #expect(command.contains("0.8"))
        #expect(command.contains("--ignored-path"))
        #expect(command.contains("metadata.trace_id"))
        #expect(command.contains("--batch-factor"))
        #expect(command.contains("--dataset-root"))
        #expect(command.contains("--few-shot"))
        #expect(command.contains("--seed"))
        #expect(command.contains("--scoring-mode"))
        #expect(command.contains("--code-exec-policy"))
        #expect(command.last == "--json")
        #expect(results.count == 1)
        #expect(first.job.jobID == "eval-compare-2")
        #expect(first.job.sourceRepo == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(first.results.count == 1)
        #expect(first.results[0].suiteID == "mmlu:melix-qwen35-acceptance")
        #expect(firstMetric.name == "eval.compare.win_rate")
        #expect(firstMetric.value == 0.625)
        #expect(firstMetric.unit == "ratio")
    }

    @Test("subprocess-backed eval compare rejects non-array JSON payloads")
    func subprocessBackedEvaluationCompareRejectsNonArrayPayloads() async throws {
        let client = StubControlPlaneXPCClient()
        let executor = RecordingCLICommandExecutor(responses: [#"{"job_id":"eval-compare-invalid"}"#])
        let runner = MelixCLIRunner(client: client, commandExecutor: executor.run)

        do {
            _ = try await runner.runEvaluationCompare(
                EvalCompareOptions(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    targetModelIDs: ["melix-qwen35-acceptance"],
                    suites: ["mmlu"]
                )
            )
            Issue.record("Expected subprocess-backed eval compare decoding to fail.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("The melix eval compare subprocess did not return a JSON array."))
        }
    }

    @Test("recording subprocess executor fails without a configured response")
    func recordingExecutorFailsWithoutAConfiguredResponse() async throws {
        let emptyExecutor = RecordingCLICommandExecutor(responses: [])

        do {
            _ = try await emptyExecutor.run(["lora", "train"])
            Issue.record("Expected the recording executor to fail without a configured response.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("No subprocess response was configured for lora train."))
        }
    }

    @Test("bench run loads the explicit model and returns JSON output")
    func benchRunLoadsExplicitModelAndReturnsJSONOutput() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setBenchResult(
            .init(
                reportPath: "/tmp/melix/bench/job-3/report.md",
                reportMarkdown: "# Melix Bench\n",
                metrics: ["bench.smoke.ttft_ms": 24.45]
            )
        )

        let output = try await MelixCLIRunner(client: client).run(
            .benchRun(
                .init(
                    modelID: "melix-dev-text",
                    suites: ["smoke", "latency"],
                    contextLengths: [2048],
                    generationLength: 256,
                    parameters: [
                        "sample_size": "8",
                        "batch_factor": "2",
                    ],
                    json: true
                )
            )
        )
        let benchRequest = try #require(await client.lastBenchRequest)
        let payload = try #require(parseJSONObject(output))
        let metrics = try #require(payload["metrics"] as? [String: Double])

        #expect(await client.loadedModelIDs == ["melix-dev-text"])
        #expect(benchRequest.modelID == "melix-dev-text")
        #expect(benchRequest.hfRepoID.isEmpty)
        #expect(benchRequest.suites == ["smoke", "latency"])
        #expect(benchRequest.contextLengths == [2048])
        #expect(benchRequest.generationLength == 256)
        #expect(benchRequest.batchSizes.isEmpty)
        #expect(benchRequest.repeats == 1)
        #expect(benchRequest.parameters["sample_size"] == "8")
        #expect(benchRequest.parameters["batch_factor"] == "2")
        #expect(payload["report_path"] as? String == "/tmp/melix/bench/job-3/report.md")
        #expect(payload["report_markdown"] as? String == "# Melix Bench\n")
        #expect(metrics["bench.smoke.ttft_ms"] == 24.45)
    }

    @Test("bench run forwards managed dataset reference parameters")
    func benchRunForwardsManagedDatasetReferenceParameters() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setBenchResult(
            .init(
                reportPath: "/tmp/melix/bench/job-dataset/report.md",
                reportMarkdown: "# Melix Bench\n",
                metrics: [:]
            )
        )

        _ = try await MelixCLIRunner(client: client).run(
            .benchRun(
                .init(
                    modelID: "melix-dev-text",
                    suites: ["latency"],
                    parameters: [
                        "dataset_ref": "Jax-dan/HundredCV-Chat@main",
                        "hf_dataset_path": "Jax-dan/HundredCV-Chat",
                        "hf_dataset_revision": "main",
                        "hf_dataset_split": "train",
                        "prompt_feature": "messages",
                    ]
                )
            )
        )
        let benchRequest = try #require(await client.lastBenchRequest)

        #expect(benchRequest.parameters["dataset_ref"] == "Jax-dan/HundredCV-Chat@main")
        #expect(benchRequest.parameters["hf_dataset_path"] == "Jax-dan/HundredCV-Chat")
        #expect(benchRequest.parameters["hf_dataset_revision"] == "main")
        #expect(benchRequest.parameters["hf_dataset_split"] == "train")
        #expect(benchRequest.parameters["prompt_feature"] == "messages")
    }

    @Test("bench run forwards canonical normalized request values")
    func benchRunForwardsCanonicalNormalizedRequestValues() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setBenchResult(
            .init(
                reportPath: "/tmp/melix/bench/job-canonical/report.md",
                reportMarkdown: "# Melix Bench\n",
                metrics: [:]
            )
        )

        _ = try await MelixCLIRunner(client: client).run(
            .benchRun(
                .init(
                    modelID: "melix-dev-text",
                    suites: ["smoke"],
                    contextLengths: [4096, 1024],
                    generationLength: 128,
                    batchSizes: [4, 2],
                    repeats: 0,
                    cacheProfile: "partial_prefix",
                    reasoningMode: "enabled",
                    structuredOutputMode: "json_schema"
                )
            )
        )
        let benchRequest = try #require(await client.lastBenchRequest)

        #expect(benchRequest.contextLengths == [1024, 4096])
        #expect(benchRequest.generationLength == 128)
        #expect(benchRequest.batchSizes == [2, 4])
        #expect(benchRequest.repeats == 1)
        #expect(benchRequest.cacheProfile == "partial_prefix")
        #expect(benchRequest.reasoningMode == "enabled")
        #expect(benchRequest.structuredOutputMode == "json_schema")
    }

    @Test("bench run forwards a direct Hugging Face repo target without preloading a catalog model")
    func benchRunForDirectHFRepoSkipsModelPreload() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setBenchResult(
            .init(
                reportPath: "/tmp/melix/bench/job-vlm/report.md",
                reportMarkdown: "# Melix Bench\n",
                metrics: ["bench.smoke.first_token_ms": 88.2]
            )
        )

        let output = try await MelixCLIRunner(client: client).run(
            .benchRun(
                .init(
                    hfRepoID: "unsloth/gemma-4-E4B-it-MLX-8bit",
                    suites: ["smoke"],
                    json: true
                )
            )
        )
        let benchRequest = try #require(await client.lastBenchRequest)
        let payload = try #require(parseJSONObject(output))

        #expect(await client.loadedModelIDs.isEmpty)
        #expect(benchRequest.modelID.isEmpty)
        #expect(benchRequest.hfRepoID == "unsloth/gemma-4-E4B-it-MLX-8bit")
        #expect(payload["report_path"] as? String == "/tmp/melix/bench/job-vlm/report.md")
    }

    @Test("bench run memory fit preflight blocks unsafe direct Hugging Face targets")
    func benchRunMemoryFitPreflightBlocksUnsafeHFRepo() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setHubModelCard(
            makeHubModelCard(
                repoID: "mlx-community/Qwen3.6-35B-A3B-4bit",
                localFitStatus: "blocked",
                localFitReasons: ["No MLX compatibility signal."],
                estimatedArtifactBytes: 24_000_000_000,
                estimatedResidentBytes: 48_000_000_000,
                recommendedAction: "Choose a smaller quantized model."
            )
        )

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .benchRun(
                    .init(
                        hfRepoID: "mlx-community/Qwen3.6-35B-A3B-4bit",
                        suites: ["smoke"],
                        preflightFitCheck: true
                    )
                )
            )
            Issue.record("Expected memory fit preflight to block the benchmark run.")
        } catch let error as MelixCLIError {
            guard case .runtime(let message) = error else {
                Issue.record("Expected runtime error.")
                return
            }
            #expect(message.contains("fit_status=blocked"))
            #expect(message.contains("estimated_active_memory_bytes=44.70 GB"))
            #expect(message.contains("estimated_disk_usage_bytes=22.35 GB"))
            #expect(message.contains("--allow-memory-risk"))
            #expect(message.contains("No MLX compatibility signal."))
        }

        #expect(await client.lastBenchRequest == nil)
    }

    @Test("bench run memory fit preflight requires a direct Hugging Face repo target")
    func benchRunMemoryFitPreflightRequiresHFRepo() async throws {
        let client = StubControlPlaneXPCClient()

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .benchRun(
                    .init(
                        modelID: "melix-dev-text",
                        suites: ["smoke"],
                        preflightFitCheck: true
                    )
                )
            )
            Issue.record("Expected memory fit preflight to reject non-Hub benchmark targets.")
        } catch let error as MelixCLIError {
            guard case .runtime(let message) = error else {
                Issue.record("Expected runtime error.")
                return
            }
            #expect(message == "--preflight-fit-check is currently supported for melix bench run --repo-id targets.")
        }

        #expect(await client.lastBenchRequest == nil)
    }

    @Test("bench run memory risk override stores the fit receipt in benchmark parameters")
    func benchRunMemoryRiskOverrideStoresFitReceiptParameters() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setHubModelCard(
            makeHubModelCard(
                repoID: "mlx-community/Qwen3.6-35B-A3B-4bit",
                localFitStatus: "heavy",
                localFitReasons: ["Estimated resident memory exceeds the comfort budget."],
                estimatedArtifactBytes: 22_000_000_000,
                estimatedResidentBytes: 44_000_000_000,
                recommendedAction: "Use --allow-memory-risk only when the Mac is otherwise idle."
            )
        )
        await client.setBenchResult(
            .init(
                reportPath: "/tmp/melix/bench/job-fit/report.md",
                reportMarkdown: "# Melix Bench\n",
                metrics: [:]
            )
        )

        _ = try await MelixCLIRunner(client: client).run(
            .benchRun(
                .init(
                    hfRepoID: "mlx-community/Qwen3.6-35B-A3B-4bit",
                    suites: ["smoke"],
                    preflightFitCheck: true,
                    allowMemoryRisk: true
                )
            )
        )
        let benchRequest = try #require(await client.lastBenchRequest)
        let receiptJSON = try #require(benchRequest.parameters["memory_fit_receipt_json"])
        let receipt = try #require(parseJSONObject(receiptJSON))

        #expect(benchRequest.hfRepoID == "mlx-community/Qwen3.6-35B-A3B-4bit")
        #expect(benchRequest.parameters["memory_fit_schema_version"] == "melix.memory_fit_receipt.v1")
        #expect(benchRequest.parameters["memory_fit_target_kind"] == "benchmark")
        #expect(benchRequest.parameters["memory_fit_status"] == "heavy")
        #expect(benchRequest.parameters["memory_fit_estimated_active_memory_bytes"] == "44000000000")
        #expect(benchRequest.parameters["memory_fit_estimated_disk_usage_bytes"] == "22000000000")
        #expect((UInt64(benchRequest.parameters["memory_fit_available_disk_bytes"] ?? "") ?? 0) > 0)
        #expect(["good", "blocked", "unknown"].contains(benchRequest.parameters["memory_fit_disk_status"] ?? ""))
        #expect(benchRequest.parameters["memory_fit_safety_threshold_fraction"] == "0.60")
        #expect(receipt["target_kind"] as? String == "benchmark")
        #expect(receipt["fit_status"] as? String == "heavy")
        #expect((receipt["probe"] as? [String: Any])?["name"] as? String == "cli.memory_fit.benchmark")
    }

    @Test("bench run returns plain markdown or the report path depending on the response")
    func benchRunReturnsPlainOutput() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setBenchResult(
            .init(
                reportPath: "/tmp/melix/bench/job-4/report.md",
                reportMarkdown: "# Bench Summary\n",
                metrics: [:]
            )
        )

        let markdown = try await MelixCLIRunner(client: client).run(
            .benchRun(.init(modelID: "melix-dev-text"))
        )
        #expect(markdown == "# Bench Summary\n")

        await client.setBenchResult(
            .init(
                reportPath: "/tmp/melix/bench/job-5/report.md",
                reportMarkdown: "",
                metrics: [:]
            )
        )

        let path = try await MelixCLIRunner(client: client).run(
            .benchRun(.init(modelID: "melix-dev-text"))
        )
        #expect(path == "/tmp/melix/bench/job-5/report.md")
    }

    @Test("bench list renders history rows and returns JSON when requested")
    func benchListRendersHistoryRowsAndJSON() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))

        let textOutput = try await MelixCLIRunner(client: client).run(.benchList(.init()))
        let jsonOutput = try await MelixCLIRunner(client: client).run(.benchList(.init(json: true)))
        let entries = try #require(parseJSONArray(jsonOutput))
        let benchOneEntry = try #require(entries.first(where: {
            ($0 as? [String: Any])?["job_id"] as? String == "bench-1"
        }) as? [String: Any])

        #expect(textOutput.contains("job_id\tmodel_id\ttask_kind\tsource_repo\tsuite\tdataset"))
        #expect(textOutput.contains("bench-1\tmelix-dev-text\ttext-generation\tHuggingFaceH4/ultrachat_200k\tsmoke\tHuggingFaceH4/ultrachat_200k/default:train_sft\t4\t2\tcompleted\t1712100000000"))
        #expect(benchOneEntry["job_id"] as? String == "bench-1")
        #expect(benchOneEntry["suite_id"] as? String == "smoke")
        #expect(benchOneEntry["dataset_repo"] as? String == "HuggingFaceH4/ultrachat_200k")
        #expect(benchOneEntry["task_kind"] as? String == "text-generation")
        #expect(benchOneEntry["source_repo"] as? String == "HuggingFaceH4/ultrachat_200k")
    }

    @Test("bench export-csv writes filtered benchmark metric rows and returns JSON metadata")
    func benchExportCSVWritesFilteredRows() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))
        let outputURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathComponent("bench-1.csv")

        let jsonOutput = try await MelixCLIRunner(client: client).run(
            .benchExportCSV(.init(jobID: "bench-1", outputPath: outputURL.path, json: true))
        )
        let response = try #require(parseJSONObject(jsonOutput))
        let csv = try String(contentsOf: outputURL, encoding: .utf8)

        #expect(response["job_id"] as? String == "bench-1")
        #expect(response["output_path"] as? String == outputURL.path)
        #expect(response["row_count"] as? Int == 2)
        #expect(csv.contains("job_id,model_id,task_kind,source_repo,suite_id,dataset_repo,dataset_config,dataset_split,sample_size,batch_factor,metric_name,metric_value,unit,created_at_unix_ms"))
        #expect(csv.contains("bench-1,melix-dev-text,text-generation,HuggingFaceH4/ultrachat_200k,smoke,HuggingFaceH4/ultrachat_200k,default,train_sft,4,2,bench.smoke.tokens_per_second,47.08,tok/s,1712100000000"))
        #expect(csv.contains("bench-1,melix-dev-text,text-generation,HuggingFaceH4/ultrachat_200k,smoke,HuggingFaceH4/ultrachat_200k,default,train_sft,4,2,bench.smoke.ttft_ms,24.45,ms,1712100000000"))
    }

    @Test("bench export-csv fails when the requested job is not present")
    func benchExportCSVFailsForMissingJob() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .benchExportCSV(.init(jobID: "bench-missing", outputPath: "/tmp/missing.csv"))
            )
            Issue.record("Expected bench export-csv to fail when the job is missing.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("No benchmark metrics were found for job bench-missing."))
        }
    }

    @Test("bench matrix run forwards normalized matrix inputs and returns JSON output")
    func benchMatrixRunForwardsNormalizedInputsAndReturnsJSON() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setBenchMatrixResult(
            .init(
                job: makeBenchmarkMatrixJobSummary(
                    jobID: "bench-matrix-1",
                    modelID: "unsloth/gemma-4-E4B-it-MLX-8bit",
                    taskKind: "image-text-to-text",
                    sourceRepo: "unsloth/gemma-4-E4B-it-MLX-8bit"
                ),
                summaryRows: [
                    makeBenchmarkMatrixSummaryRow(
                        jobID: "bench-matrix-1",
                        taskKind: "image-text-to-text",
                        sourceRepo: "unsloth/gemma-4-E4B-it-MLX-8bit",
                        modelID: "unsloth/gemma-4-E4B-it-MLX-8bit",
                        suiteID: "smoke",
                        contextLength: 1024,
                        generationLength: 128,
                        batchSize: 2,
                        cacheProfile: "cold",
                        reasoningMode: "enabled",
                        structuredOutputMode: "plain_text",
                        concurrencyLevel: 1,
                        repeats: 3,
                        requests: 24,
                        durationSeconds: 0,
                        ttftMeanMS: 44.5
                    ),
                ]
            )
        )

        let output = try await MelixCLIRunner(client: client).run(
            .benchMatrixRun(
                .init(
                    hfRepoID: "unsloth/gemma-4-E4B-it-MLX-8bit",
                    suites: ["latency", "smoke"],
                    contextLengths: [4096, 1024],
                    generationLengths: [256, 128],
                    batchSizes: [4, 2],
                    cacheProfiles: ["warm", "cold"],
                    reasoningModes: ["enabled", "disabled"],
                    structuredOutputModes: ["json_schema", "plain_text"],
                    concurrencyLevels: [8, 1],
                    repeats: 3,
                    requests: 24,
                    json: true
                )
            )
        )
        let request = try #require(await client.lastBenchMatrixRequest)
        let payload = try #require(parseJSONObject(output))
        let rows = try #require(payload["summary_rows"] as? [[String: Any]])
        let job = try #require(payload["job"] as? [String: Any])

        #expect(await client.loadedModelIDs.isEmpty)
        #expect(request.modelID.isEmpty)
        #expect(request.hfRepoID == "unsloth/gemma-4-E4B-it-MLX-8bit")
        #expect(request.suites == ["latency", "smoke"])
        #expect(request.contextLengths == [1024, 4096])
        #expect(request.generationLengths == [128, 256])
        #expect(request.batchSizes == [2, 4])
        #expect(request.cacheProfiles == ["cold", "warm"])
        #expect(request.reasoningModes == ["disabled", "enabled"])
        #expect(request.structuredOutputModes == ["json_schema", "plain_text"])
        #expect(request.concurrencyLevels == [1, 8])
        #expect(request.repeats == 3)
        #expect(request.requests == 24)
        #expect(request.durationSeconds == 0)
        #expect(job["job_id"] as? String == "bench-matrix-1")
        #expect(rows.count == 1)
        #expect(rows[0]["ttft_mean_ms"] as? Double == 44.5)
    }

    @Test("bench matrix run loads explicit models and renders tabular text output")
    func benchMatrixRunLoadsExplicitModelsAndRendersTabularTextOutput() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setBenchMatrixResult(
            .init(
                job: makeBenchmarkMatrixJobSummary(
                    jobID: "bench-matrix-2",
                    modelID: "melix-dev-text",
                    taskKind: "text-generation",
                    sourceRepo: "melix-dev-text"
                ),
                summaryRows: [
                    makeBenchmarkMatrixSummaryRow(
                        jobID: "bench-matrix-2",
                        taskKind: "text-generation",
                        sourceRepo: "melix-dev-text",
                        modelID: "melix-dev-text",
                        suiteID: "latency",
                        contextLength: 2048,
                        generationLength: 256,
                        batchSize: 4,
                        cacheProfile: "warm",
                        reasoningMode: "disabled",
                        structuredOutputMode: "json_schema",
                        concurrencyLevel: 2,
                        repeats: 2,
                        requests: 0,
                        durationSeconds: 45,
                        ttftMeanMS: 51.2
                    ),
                ]
            )
        )

        let output = try await MelixCLIRunner(client: client).run(
            .benchMatrixRun(
                .init(
                    modelID: "melix-dev-text",
                    suites: ["latency"],
                    contextLengths: [2048],
                    generationLengths: [256],
                    batchSizes: [4],
                    cacheProfiles: ["warm"],
                    reasoningModes: ["disabled"],
                    structuredOutputModes: ["json_schema"],
                    concurrencyLevels: [2],
                    repeats: 2,
                    durationSeconds: 45
                )
            )
        )

        #expect(await client.loadedModelIDs == ["melix-dev-text"])
        #expect(output.contains("job_id\tmodel_id\ttask_kind\tsource_repo\tsuite\tcontext_length"))
        #expect(output.contains("bench-matrix-2\tmelix-dev-text\ttext-generation\tmelix-dev-text\tlatency\t2048\t256\t4\twarm\tdisabled\tjson_schema\t2\t2\tduration_seconds=45\t51.2"))
    }

    @Test("bench matrix run renders the empty state when no matrix rows are returned")
    func benchMatrixRunRendersEmptyState() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setBenchMatrixResult(
            .init(
                job: makeBenchmarkMatrixJobSummary(
                    jobID: "bench-matrix-empty",
                    modelID: "melix-dev-text",
                    taskKind: "text-generation",
                    sourceRepo: "melix-dev-text"
                ),
                summaryRows: []
            )
        )

        let output = try await MelixCLIRunner(client: client).run(
            .benchMatrixRun(
                .init(
                    hfRepoID: "unsloth/gemma-4-E4B-it-MLX-8bit",
                    suites: ["smoke"],
                    contextLengths: [1024],
                    generationLengths: [128],
                    batchSizes: [2],
                    cacheProfiles: ["cold"],
                    reasoningModes: ["enabled"],
                    structuredOutputModes: ["plain_text"],
                    concurrencyLevels: [1],
                    requests: 8
                )
            )
        )

        #expect(output == "No benchmark matrix rows were returned.\n")
    }

    @Test("bench matrix list renders matrix history and returns JSON when requested")
    func benchMatrixListRendersHistoryAndReturnsJSON() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))

        let textOutput = try await MelixCLIRunner(client: client).run(.benchMatrixList(.init()))
        let jsonOutput = try await MelixCLIRunner(client: client).run(.benchMatrixList(.init(json: true)))
        let entries = try #require(parseJSONArray(jsonOutput))
        let first = try #require(entries.first as? [String: Any])

        #expect(textOutput.contains("job_id\tmodel_id\ttask_kind\tsource_repo\tsuite\tcontext_length\tgeneration_length\tbatch_size\tcache_profile\treasoning_mode\tstructured_output_mode\tconcurrency_level\trepeats\tload_budget\tstatus\tcreated_at_unix_ms"))
        #expect(textOutput.contains("bench-matrix-1\tmelix-dev-text\ttext-generation\tHuggingFaceH4/ultrachat_200k\tsmoke\t1024\t128\t2\tcold\tenabled\tplain_text\t1\t3\trequests=24\tcompleted\t1712200000000"))
        #expect(first["job_id"] as? String == "bench-matrix-1")
        #expect(first["benchmark_mode"] as? String == "matrix")
    }

    @Test("bench matrix list renders an empty state when there is no matrix history")
    func benchMatrixListRendersEmptyState() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(
            .init(exportBundleJSON: #"{"export_schema_version":"melix.benchmark_export.v1","benchmark_matrix_jobs":[],"benchmark_matrix_summary_rows":[],"benchmark_matrix_request_rows":[]}"#)
        )

        let output = try await MelixCLIRunner(client: client).run(.benchMatrixList(.init()))

        #expect(output == "No benchmark matrix runs found.\n")
    }

    @Test("bench matrix export-summary-csv writes filtered rows")
    func benchMatrixExportSummaryCSVWritesFilteredRows() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))
        let outputURL = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent(UUID().uuidString)
            .appendingPathComponent("bench-matrix-summary.csv")

        let jsonOutput = try await MelixCLIRunner(client: client).run(
            .benchMatrixExportSummaryCSV(
                .init(jobID: "bench-matrix-1", outputPath: outputURL.path, json: true)
            )
        )
        let response = try #require(parseJSONObject(jsonOutput))
        let csv = try String(contentsOf: outputURL, encoding: .utf8)

        #expect(response["job_id"] as? String == "bench-matrix-1")
        #expect(response["row_count"] as? Int == 1)
        #expect(csv.contains("job_id,task_kind,source_repo,model_id,suite_id,context_length,generation_length,batch_size,cache_profile,reasoning_mode,structured_output_mode,concurrency_level,repeats,requests,duration_seconds,ttft_mean_ms,ttft_std_ms,request_latency_mean_ms,request_latency_std_ms,prefill_tokens_per_second_mean,decode_tokens_per_second_mean,throughput_requests_per_second,throughput_tokens_per_second,success_rate,peak_memory_bytes_max,queue_wait_mean_ms,queue_wait_p95_ms,cell_wall_ms,completed_count,failed_count,ttft_p50_ms,ttft_p95_ms,request_latency_p50_ms,request_latency_p95_ms,created_at_unix_ms"))
        #expect(csv.contains("bench-matrix-1,text-generation,HuggingFaceH4/ultrachat_200k,melix-dev-text,smoke,1024,128,2,cold,enabled,plain_text,1,3,24,0,24.45,1.2,88.4,3.1,1400.0,58.2,3.8,221.5,1.0,2147483648,5.1,9.2,0.0,0,0,0.0,0.0,0.0,0.0,1712200000000"))
    }

    @Test("bench matrix export-summary-csv returns the written path in plain text")
    func benchMatrixExportSummaryCSVReturnsTheWrittenPathInPlainText() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))
        let outputURL = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent(UUID().uuidString)
            .appendingPathComponent("bench-matrix-summary.txt")

        let output = try await MelixCLIRunner(client: client).run(
            .benchMatrixExportSummaryCSV(.init(jobID: "bench-matrix-1", outputPath: outputURL.path))
        )

        #expect(output == outputURL.path + "\n")
    }

    @Test("bench matrix export-summary-csv fails when the requested job is missing")
    func benchMatrixExportSummaryCSVFailsForMissingJob() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .benchMatrixExportSummaryCSV(.init(jobID: "bench-matrix-missing", outputPath: "/tmp/missing.csv"))
            )
            Issue.record("Expected bench matrix export-summary-csv to fail when the job is missing.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("No benchmark matrix summary rows were found for job bench-matrix-missing."))
        }
    }

    @Test("bench matrix export-requests-csv writes filtered rows")
    func benchMatrixExportRequestsCSVWritesFilteredRows() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))
        let outputURL = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent(UUID().uuidString)
            .appendingPathComponent("bench-matrix-requests.csv")

        let jsonOutput = try await MelixCLIRunner(client: client).run(
            .benchMatrixExportRequestsCSV(
                .init(jobID: "bench-matrix-1", outputPath: outputURL.path, json: true)
            )
        )
        let response = try #require(parseJSONObject(jsonOutput))
        let csv = try String(contentsOf: outputURL, encoding: .utf8)

        #expect(response["job_id"] as? String == "bench-matrix-1")
        #expect(response["row_count"] as? Int == 1)
        #expect(csv.contains("job_id,cell_id,task_kind,suite_id,context_length,generation_length,batch_size,cache_profile,reasoning_mode,structured_output_mode,concurrency_level,repeat_index,request_index,ttft_ms,request_latency_ms,prefill_tokens_per_second,decode_tokens_per_second,queue_wait_ms,peak_memory_bytes,status,error_code,dataset_materialize_ms,prompt_render_ms,warmup_ms,prefill_ms,decode_ms,tokens_in,tokens_out,first_token_index,cache_hit,runtime_kind,error_stage,speculative_acceptance_rate,speculative_rollback_rate,speculative_accepted_tokens,speculative_rejected_tokens,speculative_fallback_count,speculative_num_draft_tokens,speculative_draft_model_configured,speculative_draft_propose_ms,speculative_target_verify_ms,dflash_enabled,dflash_block_size,dflash_rollback_count,dflash_target_hidden_layers,created_at_unix_ms"))
        #expect(csv.contains("bench-matrix-1,cell-1,text-generation,smoke,1024,128,2,cold,enabled,plain_text,1,0,0,24.45,88.4,1400.0,58.2,5.1,2147483648,completed,,0.0,0.0,0.0,0.0,0.0,0,0,0,false,,,0.0,0.0,0,0,0,0,false,0.0,0.0,false,0,0,0,1712200000000"))
    }

    @Test("bench matrix export-requests-csv returns the written path in plain text")
    func benchMatrixExportRequestsCSVReturnsTheWrittenPathInPlainText() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))
        let outputURL = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent(UUID().uuidString)
            .appendingPathComponent("bench-matrix-requests.txt")

        let output = try await MelixCLIRunner(client: client).run(
            .benchMatrixExportRequestsCSV(.init(jobID: "bench-matrix-1", outputPath: outputURL.path))
        )

        #expect(output == outputURL.path + "\n")
    }

    @Test("bench matrix export-requests-csv fails when the requested job is missing")
    func benchMatrixExportRequestsCSVFailsForMissingJob() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .benchMatrixExportRequestsCSV(.init(jobID: "bench-matrix-missing", outputPath: "/tmp/missing.csv"))
            )
            Issue.record("Expected bench matrix export-requests-csv to fail when the job is missing.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("No benchmark matrix request rows were found for job bench-matrix-missing."))
        }
    }

    @Test("eval run forwards sequential suite requests and returns JSON output")
    func evalRunForwardsSuiteRequestsAndReturnsJSON() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-1",
                suiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                metricName: "eval.mmlu.accuracy",
                metricValue: 0.75
            ),
            makeEvaluationRunResult(
                jobID: "eval-2",
                suiteID: "gsm8k",
                datasetID: "gsm8k.dev.v1",
                metricName: "eval.gsm8k.exact_match",
                metricValue: 0.5
            ),
        ])

        let output = try await MelixCLIRunner(client: client).run(
            .evalRun(
                .init(
                    modelID: "melix-dev-text",
                    suites: ["mmlu", "gsm8k"],
                    sampleSize: 8,
                    profile: .init(
                        resultKind: "json",
                        outputSchemaJSON: #"{"type":"object"}"#
                    ),
                    parameters: [
                        "batch_factor": "2",
                        "dataset_root": "/tmp/mmlu-split-01",
                        "few_shot": "4",
                        "hints_path": "/tmp/math-hints.md",
                        "schema_path": "/tmp/result.schema.json",
                        "seed": "7",
                        "scoring_mode": "multiple_choice_accuracy",
                        "code_exec_policy": "sandboxed",
                    ],
                    json: true
                )
            )
        )
        let payload = try #require(parseJSONArray(output))
        let requests = await client.evaluationRequests

        #expect(requests.count == 2)
        #expect(requests[0].suiteID == "mmlu")
        #expect(requests[0].datasetID == "mmlu.dev.v1")
        #expect(requests[0].sampleSize == 8)
        #expect(requests[0].parameters["batch_factor"] == "2")
        #expect(requests[0].parameters["dataset_root"] == "/tmp/mmlu-split-01")
        #expect(requests[0].parameters["few_shot"] == "4")
        #expect(requests[0].parameters["hints_path"] == "/tmp/math-hints.md")
        #expect(requests[0].parameters["schema_path"] == "/tmp/result.schema.json")
        #expect(requests[0].parameters["seed"] == "7")
        #expect(requests[0].parameters["scoring_mode"] == "multiple_choice_accuracy")
        #expect(requests[0].parameters["code_exec_policy"] == "sandboxed")
        #expect(requests[0].profile.resultKind == "json")
        #expect(requests[0].profile.outputSchemaJSON == #"{"type":"object"}"#)
        #expect(requests[1].suiteID == "gsm8k")
        #expect(requests[1].datasetID == "gsm8k.dev.v1")
        let firstRun = try #require(payload.first as? [String: Any])
        let firstJob = try #require(firstRun["job"] as? [String: Any])
        #expect(firstJob["job_id"] as? String == "eval-1")
        #expect(firstJob["suite_id"] as? String == "mmlu")
    }

    @Test("eval run memory fit preflight blocks unsafe direct Hugging Face targets")
    func evalRunMemoryFitPreflightBlocksUnsafeHFRepo() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setHubModelCard(
            makeHubModelCard(
                repoID: "mlx-community/Qwen3.6-35B-A3B-4bit",
                localFitStatus: "blocked",
                localFitReasons: ["Estimated resident memory exceeds the safety threshold."],
                estimatedArtifactBytes: 24_000_000_000,
                estimatedResidentBytes: 48_000_000_000,
                recommendedAction: "Choose a smaller evaluation target."
            )
        )

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .evalRun(
                    .init(
                        hfRepoID: "mlx-community/Qwen3.6-35B-A3B-4bit",
                        suites: ["mmlu"],
                        preflightFitCheck: true
                    )
                )
            )
            Issue.record("Expected memory fit preflight to block evaluation.")
        } catch let error as MelixCLIError {
            guard case .runtime(let message) = error else {
                Issue.record("Expected runtime error.")
                return
            }
            #expect(message.contains("blocked evaluation"))
            #expect(message.contains("fit_status=blocked"))
            #expect(message.contains("--allow-memory-risk"))
        }

        #expect(await client.evaluationRequests.isEmpty)
    }

    @Test("eval run memory risk override stores the fit receipt in request parameters")
    func evalRunMemoryRiskOverrideStoresFitReceiptParameters() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setHubModelCard(
            makeHubModelCard(
                repoID: "mlx-community/Qwen3.6-35B-A3B-4bit",
                localFitStatus: "heavy",
                localFitReasons: ["Estimated resident memory exceeds the comfort budget."],
                estimatedArtifactBytes: 22_000_000_000,
                estimatedResidentBytes: 44_000_000_000,
                recommendedAction: "Evaluate only on an idle high-memory Mac."
            )
        )
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-fit",
                suiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                metricName: "eval.mmlu.accuracy",
                metricValue: 0.5
            ),
        ])

        _ = try await MelixCLIRunner(client: client).run(
            .evalRun(
                .init(
                    hfRepoID: "mlx-community/Qwen3.6-35B-A3B-4bit",
                    suites: ["mmlu"],
                    preflightFitCheck: true,
                    allowMemoryRisk: true
                )
            )
        )
        let request = try #require(await client.evaluationRequests.first)
        let receiptJSON = try #require(request.parameters["memory_fit_receipt_json"])
        let receipt = try #require(parseJSONObject(receiptJSON))

        #expect(request.hfRepoID == "mlx-community/Qwen3.6-35B-A3B-4bit")
        #expect(request.parameters["memory_fit_schema_version"] == "melix.memory_fit_receipt.v1")
        #expect(request.parameters["memory_fit_target_kind"] == "eval")
        #expect(request.parameters["memory_fit_status"] == "heavy")
        #expect(request.parameters["memory_fit_estimated_active_memory_bytes"] == "44000000000")
        #expect((UInt64(request.parameters["memory_fit_available_disk_bytes"] ?? "") ?? 0) > 0)
        #expect(["good", "blocked", "unknown"].contains(request.parameters["memory_fit_disk_status"] ?? ""))
        #expect((receipt["unknown_fields"] as? [String])?.contains("judge_memory_bytes") == true)
        #expect((receipt["probe"] as? [String: Any])?["name"] as? String == "cli.memory_fit.eval")
    }

    @Test("eval run forwards ad hoc prompt to every evaluation suite")
    func evalRunForwardsAdHocPromptToEveryEvaluationSuite() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-adhoc-mmlu",
                suiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                metricName: "eval.mmlu.accuracy",
                metricValue: 0.75
            ),
            makeEvaluationRunResult(
                jobID: "eval-adhoc-event",
                suiteID: "event_extraction",
                datasetID: "top200.event-extraction.top20.v1",
                metricName: "eval.event_extraction.overall_weighted_f1",
                metricValue: 0.5
            ),
        ])

        _ = try await MelixCLIRunner(client: client).run(
            .evalRun(
                .init(
                    modelID: "melix-dev-text",
                    suites: ["mmlu", "event_extraction"],
                    evalPrompt: "Use this one-off evaluation rubric.",
                    json: true
                )
            )
        )

        let requests = await client.evaluationRequests
        #expect(requests.count == 2)
        for request in requests {
            #expect(request.parameters["eval_prompt_system_prompt"] == "Use this one-off evaluation rubric.")
            #expect(request.parameters["eval_prompt_id"] == "ad-hoc.evaluation.prompt")
            #expect(request.parameters["eval_prompt_revision_id"] == "ad-hoc")
            #expect(request.parameters["eval_prompt_title"] == "Ad Hoc Evaluation Prompt")
            #expect(request.parameters["eval_prompt_examples_json"] == "[]")
            #expect(request.parameters["prompt_id"] == "ad-hoc.evaluation.prompt")
            #expect(request.parameters["prompt_revision_id"] == "ad-hoc")
            #expect(request.parameters["eval_prompt_content_hash"]?.hasPrefix("sha256:") == true)
        }
    }

    @Test("eval run reads ad hoc prompt from file")
    func evalRunReadsAdHocPromptFromFile() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-adhoc-eval-prompt-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        let promptFile = temporaryRoot.appendingPathComponent("prompt.txt")
        try "  Apply the file-backed rubric.\n".write(to: promptFile, atomically: true, encoding: .utf8)

        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-adhoc-file",
                suiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                metricName: "eval.mmlu.accuracy",
                metricValue: 0.75
            ),
        ])

        _ = try await MelixCLIRunner(client: client).run(
            .evalRun(
                .init(
                    modelID: "melix-dev-text",
                    suites: ["mmlu"],
                    evalPromptFile: promptFile.path,
                    json: true
                )
            )
        )

        let request = try #require((await client.evaluationRequests).first)
        #expect(request.parameters["eval_prompt_system_prompt"] == "Apply the file-backed rubric.")
        #expect(request.parameters["eval_prompt_id"] == "ad-hoc.evaluation.prompt")
    }

    @Test("eval run defaults event extraction to the built in top20 dataset")
    func evalRunDefaultsEventExtractionToBuiltInTop20Dataset() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-event-top20",
                suiteID: "event_extraction",
                datasetID: "top200.event-extraction.top20.v1",
                metricName: "eval.event_extraction.overall_weighted_f1",
                metricValue: 0.5
            ),
        ])

        _ = try await MelixCLIRunner(client: client).run(
            .evalRun(
                .init(
                    modelID: "melix-dev-text",
                    suites: ["event_extraction"],
                    sampleSize: 20,
                    profile: .init(scoringMode: "event_extraction_weighted_f1"),
                    json: true
                )
            )
        )

        let request = try #require((await client.evaluationRequests).first)
        #expect(request.suiteID == "event_extraction")
        #expect(request.datasetID == "top200.event-extraction.top20.v1")
        #expect(request.source.kind == .builtinPackage)
        #expect(request.sampleSize == 20)
    }

    @Test("eval run dispatches multiple remote targets concurrently and preserves target order")
    func evalRunDispatchesMultipleRemoteTargetsConcurrently() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-parallel-remote-eval-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let client = StubControlPlaneXPCClient()
        await client.setEvaluationDelay(nanoseconds: 100_000_000)
        await client.setEvaluationResultsByRemoteModelID([
            "deepseek-v4-pro": makeEvaluationRunResult(
                jobID: "eval-deepseek",
                modelID: "deepseek-v4-pro",
                suiteID: "event_extraction",
                datasetID: "top200",
                metricName: "eval.event_extraction.overall_weighted_f1",
                metricValue: 0.2
            ),
            "gemini-2.5-flash": makeEvaluationRunResult(
                jobID: "eval-gemini",
                modelID: "gemini-2.5-flash",
                suiteID: "event_extraction",
                datasetID: "top200",
                metricName: "eval.event_extraction.overall_weighted_f1",
                metricValue: 0.3
            ),
        ])

        let runner = MelixCLIRunner(client: client, environment: ["MELIX_HOME": temporaryRoot.path])
        _ = try await runner.run(
            .remoteServerAdd(
                .init(
                    remoteServerID: "DeepSeek",
                    title: "DeepSeek",
                    providerPreset: .deepseek,
                    defaultModelID: "deepseek-v4-pro",
                    apiKey: "sk-deepseek"
                )
            )
        )
        _ = try await runner.run(
            .remoteServerAdd(
                .init(
                    remoteServerID: "Gemini",
                    title: "Gemini",
                    providerPreset: .gemini,
                    defaultModelID: "gemini-2.5-flash",
                    apiKey: "sk-gemini"
                )
            )
        )

        let results = try await runner.runEvaluations(
            .init(
                remoteTargets: [
                    EvalRemoteTargetOptions(remoteServerID: "DeepSeek", remoteModelID: ""),
                    EvalRemoteTargetOptions(remoteServerID: "Gemini", remoteModelID: ""),
                ],
                suites: ["event_extraction"],
                datasetID: "top200",
                sampleSize: 1,
                profile: .init(scoringMode: "event_extraction_weighted_f1"),
                remoteParallelism: 2
            )
        )
        let requests = await client.evaluationRequests

        #expect(results.map(\.job.modelID) == ["deepseek-v4-pro", "gemini-2.5-flash"])
        #expect(await client.maxConcurrentEvaluationCalls == 2)
        let remoteRequests = requests
            .map {
                (
                    serverID: $0.remoteTarget?.remoteServerID ?? "",
                    apiKey: $0.remoteTarget?.apiKey ?? "",
                    modelID: $0.remoteTarget?.modelID ?? ""
                )
            }
            .sorted { $0.serverID < $1.serverID }
        #expect(remoteRequests.map(\.serverID) == ["DeepSeek", "Gemini"])
        #expect(remoteRequests.map(\.apiKey) == ["sk-deepseek", "sk-gemini"])
        #expect(remoteRequests.map(\.modelID) == ["deepseek-v4-pro", "gemini-2.5-flash"])
    }

    @Test("eval run renders tabular text output for completed suites")
    func evalRunRendersTextOutput() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-1",
                suiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                metricName: "eval.mmlu.accuracy",
                metricValue: 0.75
            ),
        ])

        let output = try await MelixCLIRunner(client: client).run(
            .evalRun(
                .init(
                    modelID: "melix-dev-text",
                    sampleSize: 8
                )
            )
        )
        let request = try #require((await client.evaluationRequests).first)

        #expect(request.suiteID == "mmlu")
        #expect(request.datasetID == "mmlu.dev.v1")
        #expect(output.contains("job_id\tsuite\tdataset\tstatus\tmetrics"))
        #expect(output.contains("eval-1\tmmlu\tmmlu.dev.v1\tcompleted\teval.mmlu.accuracy=0.75ratio"))
    }

    @Test("eval run forwards custom Hugging Face dataset source mapping and profile controls")
    func evalRunForwardsCustomHFDatasetSourceMappingAndProfileControls() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-hf-custom-1",
                suiteID: "dolly",
                datasetID: "databricks-dolly-15k.dev.v1",
                metricName: "eval.dolly.exact_match",
                metricValue: 0.5
            ),
        ])

        _ = try await MelixCLIRunner(client: client).run(
            .evalRun(
                .init(
                    hfRepoID: "unsloth/gemma-4-E4B-it-MLX-8bit",
                    suites: ["dolly"],
                    source: .huggingFaceDataset(
                        datasetPath: "databricks/databricks-dolly-15k",
                        datasetRevision: "main",
                        split: "train"
                    ),
                    fieldMapping: .init(
                        inputTextPath: "instruction",
                        targetPath: "response",
                        sampleIDPath: "sample_id"
                    ),
                    profile: .init(
                        profileType: "final_result",
                        resultKind: "text",
                        extractionMode: "heuristic_final",
                        scoringMode: "normalized_exact_match",
                        threshold: 1.0,
                        ignoredPaths: ["metadata.trace_id"]
                    ),
                    parameters: [
                        "scoring_mode": "normalized_exact_match",
                    ]
                )
            )
        )
        let request = try #require((await client.evaluationRequests).first)

        #expect(request.datasetID.isEmpty)
        #expect(request.source.kind == .huggingFaceDataset)
        #expect(request.source.datasetPath == "databricks/databricks-dolly-15k")
        #expect(request.source.datasetRevision == "main")
        #expect(request.source.split == "train")
        #expect(request.fieldMapping.inputTextPath == "instruction")
        #expect(request.fieldMapping.targetPath == "response")
        #expect(request.fieldMapping.sampleIDPath == "sample_id")
        #expect(request.profile.resultKind == "text")
        #expect(request.profile.extractionMode == "heuristic_final")
        #expect(request.profile.scoringMode == "normalized_exact_match")
        #expect(request.profile.threshold == 1.0)
        #expect(request.profile.ignoredPaths == ["metadata.trace_id"])
    }

    @Test("eval run forwards managed dataset reference parameters")
    func evalRunForwardsManagedDatasetReferenceParameters() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-managed-dataset",
                suiteID: "dolly",
                datasetID: "managed.dev.v1",
                metricName: "eval.dolly.exact_match",
                metricValue: 0.5
            ),
        ])

        _ = try await MelixCLIRunner(client: client).run(
            .evalRun(
                .init(
                    modelID: "melix-dev-text",
                    suites: ["dolly"],
                    source: .huggingFaceDataset(
                        datasetPath: "IRUCAAI/extract_group_chat_dataset_with_summary",
                        datasetRevision: "main",
                        split: "train"
                    ),
                    fieldMapping: .init(inputTextPath: "dialogue", targetPath: "summary"),
                    parameters: [
                        "dataset_ref": "IRUCAAI/extract_group_chat_dataset_with_summary@main",
                        "hf_dataset_path": "IRUCAAI/extract_group_chat_dataset_with_summary",
                        "hf_dataset_revision": "main",
                    ]
                )
            )
        )
        let request = try #require((await client.evaluationRequests).first)

        #expect(request.source.kind == .huggingFaceDataset)
        #expect(request.source.datasetPath == "IRUCAAI/extract_group_chat_dataset_with_summary")
        #expect(request.source.datasetRevision == "main")
        #expect(request.parameters["dataset_ref"] == "IRUCAAI/extract_group_chat_dataset_with_summary@main")
        #expect(request.parameters["hf_dataset_path"] == "IRUCAAI/extract_group_chat_dataset_with_summary")
        #expect(request.parameters["hf_dataset_revision"] == "main")
    }

    @Test("eval compare preloads base and target models and forwards comparison parameters")
    func evalComparePreloadsBaseAndTargetsAndReturnsJSON() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-compare-1",
                suiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                metricName: "eval.compare.win_rate",
                metricValue: 0.5
            ),
        ])

        let output = try await MelixCLIRunner(client: client).run(
            .evalCompare(
                .init(
                    modelID: "melix-dev-text",
                    targetModelIDs: ["melix-dev-text-lora-a", "melix-dev-text-lora-b"],
                    suites: ["mmlu"],
                    datasetID: "mmlu.dev.v1",
                    sampleSize: 8,
                    parameters: [
                        "batch_factor": "2",
                        "dataset_root": "/tmp/mmlu-split-01",
                        "few_shot": "4",
                        "seed": "7",
                        "scoring_mode": "multiple_choice_accuracy",
                        "code_exec_policy": "sandboxed",
                    ],
                    json: true
                )
            )
        )
        let requests = await client.evaluationRequests
        let payload = try #require(parseJSONArray(output))
        let firstRun = try #require(payload.first as? [String: Any])
        let firstJob = try #require(firstRun["job"] as? [String: Any])

        #expect(await client.loadedModelIDs == ["melix-dev-text", "melix-dev-text-lora-a", "melix-dev-text-lora-b"])
        #expect(requests.count == 1)
        #expect(requests[0].modelID == "melix-dev-text")
        #expect(requests[0].suiteID == "mmlu")
        #expect(requests[0].datasetID == "mmlu.dev.v1")
        #expect(requests[0].sampleSize == 8)
        #expect(requests[0].parameters["compare_mode"] == "base_vs_targets")
        #expect(requests[0].parameters["compare_target_model_ids"] == "melix-dev-text-lora-a,melix-dev-text-lora-b")
        #expect(requests[0].parameters["batch_factor"] == "2")
        #expect(requests[0].parameters["dataset_root"] == "/tmp/mmlu-split-01")
        #expect(requests[0].parameters["few_shot"] == "4")
        #expect(requests[0].parameters["seed"] == "7")
        #expect(requests[0].parameters["scoring_mode"] == "multiple_choice_accuracy")
        #expect(requests[0].parameters["code_exec_policy"] == "sandboxed")
        #expect(firstJob["job_id"] as? String == "eval-compare-1")
        #expect(firstJob["suite_id"] as? String == "mmlu")
    }

    @Test("eval compare forwards custom JSONL source mapping and profile controls")
    func evalCompareForwardsCustomJSONLSourceMappingAndProfileControls() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-compare-custom-1",
                suiteID: "mmlu",
                datasetID: "mmlu-jsonl.dev.v1",
                metricName: "eval.compare.win_rate",
                metricValue: 0.5
            ),
        ])

        _ = try await MelixCLIRunner(client: client).run(
            .evalCompare(
                .init(
                    modelID: "melix-dev-text",
                    targetModelIDs: ["melix-dev-text-lora"],
                    suites: ["mmlu"],
                    source: .localJSONL(path: "/tmp/eval/mmlu.jsonl"),
                    fieldMapping: .init(
                        inputTextPath: "prompt",
                        targetPath: "expected",
                        sampleIDPath: "sample_id"
                    ),
                    profile: .init(
                        profileType: "final_result",
                        resultKind: "text",
                        extractionMode: "heuristic_final",
                        scoringMode: "normalized_exact_match",
                        threshold: 0.8,
                        ignoredPaths: ["metadata.trace_id"]
                    ),
                    parameters: [
                        "scoring_mode": "normalized_exact_match",
                    ],
                    json: true
                )
            )
        )
        let request = try #require((await client.evaluationRequests).first)

        #expect(await client.loadedModelIDs == ["melix-dev-text", "melix-dev-text-lora"])
        #expect(request.datasetID.isEmpty)
        #expect(request.parameters["compare_mode"] == "base_vs_targets")
        #expect(request.parameters["compare_target_model_ids"] == "melix-dev-text-lora")
        #expect(request.source.kind == .localJSONL)
        #expect(request.source.path == "/tmp/eval/mmlu.jsonl")
        #expect(request.fieldMapping.inputTextPath == "prompt")
        #expect(request.fieldMapping.targetPath == "expected")
        #expect(request.fieldMapping.sampleIDPath == "sample_id")
        #expect(request.profile.resultKind == "text")
        #expect(request.profile.extractionMode == "heuristic_final")
        #expect(request.profile.scoringMode == "normalized_exact_match")
        #expect(request.profile.threshold == 0.8)
        #expect(request.profile.ignoredPaths == ["metadata.trace_id"])
    }

    @Test("eval compare forwards managed dataset reference parameters")
    func evalCompareForwardsManagedDatasetReferenceParameters() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-compare-managed-dataset",
                suiteID: "dolly",
                datasetID: "managed.dev.v1",
                metricName: "eval.compare.win_rate",
                metricValue: 0.5
            ),
        ])

        _ = try await MelixCLIRunner(client: client).run(
            .evalCompare(
                .init(
                    modelID: "melix-dev-text",
                    targetModelIDs: ["melix-dev-text-lora"],
                    suites: ["dolly"],
                    source: .huggingFaceDataset(
                        datasetPath: "IRUCAAI/extract_group_chat_dataset_with_summary",
                        datasetRevision: "main",
                        split: "train"
                    ),
                    fieldMapping: .init(inputTextPath: "dialogue", targetPath: "summary"),
                    parameters: [
                        "dataset_ref": "IRUCAAI/extract_group_chat_dataset_with_summary@main",
                        "hf_dataset_path": "IRUCAAI/extract_group_chat_dataset_with_summary",
                        "hf_dataset_revision": "main",
                    ],
                    json: true
                )
            )
        )
        let request = try #require((await client.evaluationRequests).first)

        #expect(await client.loadedModelIDs == ["melix-dev-text", "melix-dev-text-lora"])
        #expect(request.parameters["compare_mode"] == "base_vs_targets")
        #expect(request.parameters["compare_target_model_ids"] == "melix-dev-text-lora")
        #expect(request.source.kind == .huggingFaceDataset)
        #expect(request.source.datasetPath == "IRUCAAI/extract_group_chat_dataset_with_summary")
        #expect(request.source.datasetRevision == "main")
        #expect(request.parameters["dataset_ref"] == "IRUCAAI/extract_group_chat_dataset_with_summary@main")
        #expect(request.parameters["hf_dataset_path"] == "IRUCAAI/extract_group_chat_dataset_with_summary")
        #expect(request.parameters["hf_dataset_revision"] == "main")
    }

    @Test("eval compare rejects requests without target models before dispatch")
    func evalCompareRejectsMissingTargetsBeforeDispatch() async throws {
        let client = StubControlPlaneXPCClient()

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .evalCompare(
                    .init(
                        modelID: "melix-dev-text",
                        suites: ["mmlu"],
                        datasetID: "mmlu.dev.v1",
                        sampleSize: 8
                    )
                )
            )
            Issue.record("Expected eval compare to fail when no target models are provided.")
        } catch let error as MelixCLIError {
            #expect(error == .missingRequired("At least one --target-model-id or --target-adapter is required for melix eval compare."))
        }

        #expect(await client.loadedModelIDs.isEmpty)
        #expect(await client.evaluationRequests.isEmpty)
    }

    @Test("eval compare renders one text row per comparison result")
    func evalCompareRendersTextOutputRows() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationCompareResult(
                jobID: "eval-compare-2",
                baseSuiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                targets: [
                    ("melix-dev-text-lora-a", 0.625),
                    ("melix-dev-text-lora-b", 0.375),
                ]
            ),
        ])
        await client.setExportResult(.init(exportBundleJSON: makeEvaluationCompareExportBundleJSON()))
        let output = try await MelixCLIRunner(client: client).run(
            .evalCompare(
                .init(
                    modelID: "melix-dev-text",
                    targetModelIDs: ["melix-dev-text-lora-a", "melix-dev-text-lora-b"],
                    suites: ["mmlu"],
                    datasetID: "mmlu.dev.v1",
                    sampleSize: 8
                )
            )
        )

        #expect(output.contains("job_id\tsuite\tdataset\tstatus\tverdict\tdelta\tbootstrap_ci\tanalytical_ci\tthreshold"))
        #expect(output.contains("eval-compare-2\tmmlu:melix-dev-text-lora-a\tmmlu.dev.v1\tcompleted\timprovement\t+0.2500\t[+0.1200, +0.4100]\t[+0.1000, +0.3800]\t0.1000"))
        #expect(output.contains("eval-compare-2\tmmlu:melix-dev-text-lora-b\tmmlu.dev.v1\tcompleted\tinconclusive\t-0.1250\t[-0.2100, +0.0200]\t[-0.1800, +0.0100]\t0.1000"))
    }

    @Test("eval compare falls back to metrics table when compare summary rows are unavailable")
    func evalCompareFallsBackToMetricsTableWithoutCompareSummaryRows() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationCompareResult(
                jobID: "eval-compare-2",
                baseSuiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                targets: [
                    ("melix-dev-text-lora-a", 0.625),
                ]
            ),
        ])
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))

        let output = try await MelixCLIRunner(client: client).run(
            .evalCompare(
                .init(
                    modelID: "melix-dev-text",
                    targetModelIDs: ["melix-dev-text-lora-a"],
                    suites: ["mmlu"],
                    datasetID: "mmlu.dev.v1",
                    sampleSize: 8
                )
            )
        )

        #expect(output.contains("job_id\tsuite\tdataset\tstatus\tmetrics"))
        #expect(output.contains("eval-compare-2\tmmlu:melix-dev-text-lora-a\tmmlu.dev.v1\tcompleted\teval.compare.win_rate=0.625ratio"))
    }

    @Test("eval compare renders suite fallback and placeholder evidence markers")
    func evalCompareRendersSuiteFallbackAndPlaceholderEvidenceMarkers() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationCompareResult(
                jobID: "eval-compare-2",
                baseSuiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                targets: [
                    ("melix-dev-text-lora-a", 0.625),
                ]
            ),
        ])
        await client.setExportResult(.init(exportBundleJSON: makeEvaluationCompareSparseExportBundleJSON()))

        let output = try await MelixCLIRunner(client: client).run(
            .evalCompare(
                .init(
                    modelID: "melix-dev-text",
                    targetModelIDs: ["melix-dev-text-lora-a"],
                    suites: ["mmlu"],
                    datasetID: "mmlu.dev.v1",
                    sampleSize: 8
                )
            )
        )

        #expect(output.contains("job_id\tsuite\tdataset\tstatus\tverdict\tdelta\tbootstrap_ci\tanalytical_ci\tthreshold"))
        #expect(output.contains("eval-compare-2\tmmlu\tmmlu.dev.v1\tcompleted\tinconclusive\t-0.1250\t-\t-\t-"))
    }

    @Test("eval compare tolerates duplicate job identifiers in status mapping")
    func evalCompareToleratesDuplicateJobIdentifiersInStatusMapping() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationCompareResult(
                jobID: "eval-compare-2",
                baseSuiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                targets: [
                    ("melix-dev-text-lora-a", 0.625),
                ],
                status: "queued"
            ),
            makeEvaluationCompareResult(
                jobID: "eval-compare-2",
                baseSuiteID: "arc",
                datasetID: "mmlu.dev.v1",
                targets: [
                    ("melix-dev-text-lora-a", 0.625),
                ],
                status: "completed"
            ),
        ])
        await client.setExportResult(.init(exportBundleJSON: makeEvaluationCompareExportBundleJSON()))

        let output = try await MelixCLIRunner(client: client).run(
            .evalCompare(
                .init(
                    modelID: "melix-dev-text",
                    targetModelIDs: ["melix-dev-text-lora-a"],
                    suites: ["mmlu", "arc"],
                    datasetID: "mmlu.dev.v1",
                    sampleSize: 8
                )
            )
        )

        let matchingRows = output.split(separator: "\n").filter {
            $0.contains("eval-compare-2\tmmlu:melix-dev-text-lora-a\tmmlu.dev.v1\tcompleted\timprovement")
        }
        #expect(matchingRows.count == 1)
    }

    @Test("eval list renders history rows and returns JSON when requested")
    func evalListRendersHistoryRowsAndJSON() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))

        let textOutput = try await MelixCLIRunner(client: client).run(.evalList(.init()))
        let jsonOutput = try await MelixCLIRunner(client: client).run(.evalList(.init(json: true)))
        let entries = try #require(parseJSONArray(jsonOutput))
        let evalEntry = try #require(entries.first as? [String: Any])

        #expect(textOutput.contains("job_id\tmodel_id\ttask_kind\tsource_repo\tsuite\tdataset\tsample_size\tscoring_mode\tstatus\tcreated_at_unix_ms"))
        #expect(textOutput.contains("eval-1\tmelix-dev-text\ttext-generation\tHuggingFaceH4/ultrachat_200k\tmmlu\tmmlu.dev.v1\t8\tmultiple_choice_accuracy\tcompleted\t1712400000000"))
        #expect(evalEntry["job_id"] as? String == "eval-1")
        #expect(evalEntry["suite_id"] as? String == "mmlu")
        #expect(evalEntry["task_kind"] as? String == "text-generation")
    }

    @Test("eval list renders the empty history state when no evaluation jobs are present")
    func evalListRendersEmptyState() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeEmptyBenchmarkExportBundleJSON()))

        let output = try await MelixCLIRunner(client: client).run(.evalList(.init()))

        #expect(output == "No evaluation runs found.\n")
    }

    @Test("eval export commands write summary csv and sample artifacts with code evidence")
    func evalExportCommandsWriteArtifacts() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let summaryURL = root.appendingPathComponent("eval-1-summary.csv")
        let samplesURL = root.appendingPathComponent("eval-1-samples.csv")
        let jsonlURL = root.appendingPathComponent("eval-1-samples.jsonl")

        let summaryOutput = try await MelixCLIRunner(client: client).run(
            .evalExportSummaryCSV(.init(jobID: "eval-1", outputPath: summaryURL.path, json: true))
        )
        _ = try await MelixCLIRunner(client: client).run(
            .evalExportSamplesCSV(.init(jobID: "eval-1", outputPath: samplesURL.path))
        )
        _ = try await MelixCLIRunner(client: client).run(
            .evalExportSamplesJSONL(.init(jobID: "eval-1", outputPath: jsonlURL.path))
        )

        let response = try #require(parseJSONObject(summaryOutput))
        let summaryCSV = try String(contentsOf: summaryURL, encoding: .utf8)
        let samplesCSV = try String(contentsOf: samplesURL, encoding: .utf8)
        let samplesJSONL = try String(contentsOf: jsonlURL, encoding: .utf8)

        #expect(response["job_id"] as? String == "eval-1")
        #expect(response["row_count"] as? Int == 1)
        #expect(summaryCSV.contains("job_id,model_id,task_kind,source_repo,suite_id,dataset_id,sample_size,primary_score_name,primary_score_value,extraction_success_count,validation_success_count,scored_sample_count,failure_count,effect_threshold,verdict,bootstrap_lower_bound,bootstrap_upper_bound,analytical_lower_bound,analytical_upper_bound,duration_seconds,created_at_unix_ms"))
        #expect(summaryCSV.contains("eval-1,melix-dev-text,text-generation,HuggingFaceH4/ultrachat_200k,mmlu,mmlu.dev.v1,8,eval.mmlu.accuracy,0.75,8,8,8,0,0.1,improvement,0.12,0.41,0.1,0.38,12.5,1712400000000"))
        #expect(samplesCSV.contains("job_id,suite_id,id,task_kind,target,extracted_result,input_text,raw_response,typed_score,time_s,extraction_status,validation_status,failure_reason,input_modalities,media_references,code_language,code_entry_point,code_compile_status,code_runtime_status,code_timeout_status,code_test_status,code_tests_passed,code_tests_total,code_failure_detail,category_label,subject_label"))
        #expect(samplesCSV.contains("eval-1,mmlu,sample-1,text-generation,4,4,2+2?,4,1.0,0.01,extracted,validated,,text,,python,solve,compiled,ok,ok,passed,2,2,,math,algebra"))
        #expect(samplesJSONL.contains("\"sample_id\":\"sample-1\""))
        #expect(samplesJSONL.contains("\"task_kind\":\"text-generation\""))
        #expect(samplesJSONL.contains("\"code_language\":\"python\""))
    }

    @Test("eval compare export commands write summary csv and sample artifacts")
    func evalCompareExportCommandsWriteArtifacts() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let summaryURL = root.appendingPathComponent("eval-compare-1-summary.csv")
        let samplesURL = root.appendingPathComponent("eval-compare-1-samples.csv")
        let jsonlURL = root.appendingPathComponent("eval-compare-1-samples.jsonl")

        let summaryOutput = try await MelixCLIRunner(client: client).run(
            .evalCompareExportSummaryCSV(.init(jobID: "eval-compare-1", outputPath: summaryURL.path, json: true))
        )
        _ = try await MelixCLIRunner(client: client).run(
            .evalCompareExportSamplesCSV(.init(jobID: "eval-compare-1", outputPath: samplesURL.path))
        )
        _ = try await MelixCLIRunner(client: client).run(
            .evalCompareExportSamplesJSONL(.init(jobID: "eval-compare-1", outputPath: jsonlURL.path))
        )

        let response = try #require(parseJSONObject(summaryOutput))
        let summaryCSV = try String(contentsOf: summaryURL, encoding: .utf8)
        let samplesCSV = try String(contentsOf: samplesURL, encoding: .utf8)
        let samplesJSONL = try String(contentsOf: jsonlURL, encoding: .utf8)

        #expect(response["job_id"] as? String == "eval-compare-1")
        #expect(response["row_count"] as? Int == 1)
        #expect(summaryCSV.contains("job_id,base_model_id,target_model_id,suite_id,dataset_id,sample_size,win_count,loss_count,tie_count,regression_count,base_accuracy,target_accuracy,delta_accuracy,duration_seconds"))
        #expect(summaryCSV.contains("eval-compare-1,melix-dev-text,melix-dev-text-lora-a,mbpp,mbpp.dev.v1,2,1,0,1,0,0.5,1.0,0.5,1.75"))
        #expect(samplesCSV.contains("job_id,suite_id,dataset_id,sample_id,target_model_id,input_text,target,base_extracted_result,target_extracted_result,base_raw_response,target_raw_response,base_typed_score,target_typed_score,outcome,regression_kind,base_time_s,target_time_s,base_extraction_status,target_extraction_status,base_validation_status,target_validation_status,base_failure_reason,target_failure_reason,base_parse_status,target_parse_status,code_language,code_entry_point"))
        #expect(samplesCSV.contains("eval-compare-1,mbpp,mbpp.dev.v1,sample-1,melix-dev-text-lora-a,Write solve(n) that returns n,solve,\"def solve(n):"))
        #expect(samplesCSV.contains("parsed_code_fallback,parsed_code_fallback"))
        #expect(samplesCSV.contains("python,solve,compiled,compiled,ok,ok,ok,ok,failed,passed,1,2,2,2,assertion failed,"))
        #expect(samplesJSONL.contains("\"target_model_id\":\"melix-dev-text-lora-a\""))
        #expect(samplesJSONL.contains("\"base_code_failure_detail\":\"assertion failed\""))
    }

    @Test("eval export commands fail when the requested job has no rows")
    func evalExportCommandsFailForMissingJob() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .evalExportSummaryCSV(.init(jobID: "eval-missing", outputPath: "/tmp/eval-missing.csv"))
            )
            Issue.record("Expected eval export-summary-csv to fail when the job is missing.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("No evaluation rows were found for job eval-missing."))
        }
    }

    @Test("eval compare export commands fail when the requested job has no rows")
    func evalCompareExportCommandsFailForMissingJob() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .evalCompareExportSummaryCSV(.init(jobID: "eval-compare-missing", outputPath: "/tmp/eval-compare-missing.csv"))
            )
            Issue.record("Expected eval compare export-summary-csv to fail when the job is missing.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("No evaluation compare summary rows were found for job eval-compare-missing."))
        }
    }

    @Test("runner default live client path uses the supplied environment-backed service builder")
    func runnerDefaultLiveClientPathUsesServiceBuilder() async throws {
        let recorder = EnvironmentRecorder()
        let runner = MelixCLIRunner(
            environment: [
                "MELIX_REPO_ROOT": "/tmp/melix-repo",
                "MELIX_WORKER_SOCKET_PATH": "/tmp/melix-python.sock",
                "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": "/tmp/melix-swift.sock",
            ],
            serviceBuilder: { environment in
                recorder.record(environment)
                return ExportResultsOnlyControlPlaneService(exportBundleJSON: makeBenchmarkExportBundleJSON())
            }
        )

        let output = try await runner.run(.benchList(.init()))
        let environment = try #require(recorder.environment)

        #expect(environment["MELIX_REPO_ROOT"] == "/tmp/melix-repo")
        #expect(environment["MELIX_WORKER_SOCKET_PATH"] == "/tmp/melix-python.sock")
        #expect(environment["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"] == "/tmp/melix-swift.sock")
        #expect(output.contains("bench-1\tmelix-dev-text\ttext-generation\tHuggingFaceH4/ultrachat_200k\tsmoke"))
    }

    @Test("default runner instantiates the built-in local runtime with an explicit repo root")
    func defaultRunnerInstantiatesLocalRuntimeWithExplicitRepoRoot() {
        let repoRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .path

        _ = MelixCLIRunner(
            environment: [
                "MELIX_REPO_ROOT": repoRoot,
                "MELIX_WORKER_SOCKET_PATH": "/tmp/melix-python.sock",
                "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": "/tmp/melix-swift.sock",
            ]
        )

        #expect(Bool(true))
    }

    @Test("default runner falls back to the repository path when MELIX_REPO_ROOT is absent")
    func defaultRunnerInstantiatesLocalRuntimeWithFallbackRepoRoot() {
        _ = MelixCLIRunner(
            environment: [
                "MELIX_WORKER_SOCKET_PATH": "/tmp/melix-python.sock",
                "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": "/tmp/melix-swift.sock",
            ]
        )

        #expect(Bool(true))
    }

    @Test("diagnostics probe policy uses safe defaults unless debug mode is requested")
    func diagnosticsProbePolicyPayloadUsesSafeDefaults() {
        let emptyPolicy = MelixDiagnosticsStore.probePolicyPayload(environment: [:])
        #expect(emptyPolicy["mode"] as? String == "minimal")
        #expect(emptyPolicy["fallback_applied"] as? Bool == false)
        #expect(emptyPolicy["detailed_telemetry_enabled"] as? Bool == false)
        #expect(emptyPolicy["debug_artifacts_enabled"] as? Bool == false)

        let invalidPolicy = MelixDiagnosticsStore.probePolicyPayload(
            environment: ["MELIX_PROBE_MODE": "unexpected"]
        )
        #expect(invalidPolicy["mode"] as? String == "minimal")
        #expect(invalidPolicy["fallback_applied"] as? Bool == true)
        #expect(invalidPolicy["detailed_telemetry_enabled"] as? Bool == false)
        #expect(invalidPolicy["debug_artifacts_enabled"] as? Bool == false)

        let debugPolicy = MelixDiagnosticsStore.probePolicyPayload(
            environment: ["MELIX_PROBE_MODE": "debug"]
        )
        #expect(debugPolicy["mode"] as? String == "debug")
        #expect(debugPolicy["fallback_applied"] as? Bool == false)
        #expect(debugPolicy["detailed_telemetry_enabled"] as? Bool == true)
        #expect(debugPolicy["debug_artifacts_enabled"] as? Bool == true)
    }

    @Test("lora list fails when the server snapshot has no models")
    func loraListFailsWhenServerSnapshotIsEmpty() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(models: []))

        do {
            _ = try await MelixCLIRunner(client: client).run(.loraList(.init()))
            Issue.record("Expected lora list to fail without an available model.")
        } catch let error as MelixCLIError {
            #expect(
                error == .missingRequired("No model is available in the current server snapshot.")
            )
        }
    }

    @Test("offline run record commands list show export and report local artifacts")
    func offlineRunRecordCommandsListShowExportAndReportLocalArtifacts() async throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-run-records-\(UUID().uuidString)")
        let sourceRoot = root.appendingPathComponent("records", isDirectory: true)
        let benchRunRoot = sourceRoot.appendingPathComponent("bench-1", isDirectory: true)
        let evalRunRoot = sourceRoot.appendingPathComponent("eval-1", isDirectory: true)
        try FileManager.default.createDirectory(at: benchRunRoot, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: evalRunRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        try writeJSONObjectForTest(
            makeRunRecordPayloadForTest(
                runID: "bench-1",
                runKind: "benchmark",
                runRoot: benchRunRoot,
                startedAtUnixMS: 200,
                command: "melix bench run --model-id melix-dev-text --suite smoke --local-inference-smoke-prompt hidden-prompt-token",
                parameters: [
                    "sample_size": "2",
                    "prompt": "hidden-prompt-token",
                    "authorization_header": "Authorization: Bearer sk-secret-header",
                    "artifact_path": "/Users/alice/.melix/secrets/sk-secret-path/model",
                ]
            ),
            to: benchRunRoot.appendingPathComponent("run-record.json")
        )
        try writeJSONObjectForTest(
            makeRunRecordPayloadForTest(
                runID: "eval-1",
                runKind: "evaluation",
                runRoot: evalRunRoot,
                startedAtUnixMS: 100,
                metricName: "eval.mmlu.accuracy",
                metricUnit: "ratio"
            ),
            to: evalRunRoot.appendingPathComponent("run-record.json")
        )
        try "Authorization: Bearer sk-secret-log\nbenchmark failed after import\n"
            .write(to: benchRunRoot.appendingPathComponent("logs.txt"), atomically: true, encoding: .utf8)
        try "active line 1\n"
            .write(to: evalRunRoot.appendingPathComponent("logs.txt"), atomically: true, encoding: .utf8)

        let runner = MelixCLIRunner(
            client: StubControlPlaneXPCClient(),
            environment: [
                "MELIX_HOME": root.path,
                "MELIX_API_KEY": "sk-secret-env",
                "MELIX_LOGS_DIR": root.appendingPathComponent("logs").path,
                "MELIX_PROBE_MODE": "debug",
            ]
        )

        let listJSON = try await runner.run(.runsList(.init(sourcePath: sourceRoot.path, json: true)))
        let listPayload = try #require(parseJSONArray(listJSON) as? [[String: Any]])
        #expect(listPayload.count == 2)
        #expect(listPayload[0]["run_id"] as? String == "bench-1")
        #expect(listPayload[1]["run_id"] as? String == "eval-1")

        let listText = try await runner.run(.runsList(.init(sourcePath: sourceRoot.path)))
        #expect(listText.contains("run_id\trun_kind\tstatus"))
        #expect(listText.contains("bench-1\tbenchmark\tcompleted"))

        let showMarkdown = try await runner.run(.runsShow(.init(runID: "bench-1", sourcePath: sourceRoot.path)))
        #expect(showMarkdown.contains("# Melix Run bench-1"))
        #expect(showMarkdown.contains("## Reproduction Command"))
        #expect(showMarkdown.contains("melix bench run --model-id melix-dev-text"))

        let showJSON = try await runner.run(.runsShow(.init(runID: "bench-1", sourcePath: sourceRoot.path, json: true)))
        #expect(parseJSONObject(showJSON)?["run_id"] as? String == "bench-1")

        let fileSourceMarkdown = try await runner.run(
            .runsShow(
                .init(
                    runID: "bench-1",
                    sourcePath: benchRunRoot.appendingPathComponent("run-record.json").path
                )
            )
        )
        #expect(fileSourceMarkdown.contains("# Melix Run bench-1"))

        let exportURL = root.appendingPathComponent("exports/bench-1.md")
        let exportOutput = try await runner.run(
            .runsExport(.init(runID: "bench-1", sourcePath: sourceRoot.path, format: "md", outputPath: exportURL.path))
        )
        #expect(exportOutput == exportURL.path + "\n")
        #expect(try String(contentsOf: exportURL, encoding: .utf8).contains("# Melix Run bench-1"))

        let exportJSON = try await runner.run(.runsExport(.init(runID: "bench-1", sourcePath: sourceRoot.path, format: "json")))
        #expect(parseJSONObject(exportJSON)?["run_id"] as? String == "bench-1")

        let benchReportMarkdown = try await runner.run(.benchReport(.init(sourcePath: sourceRoot.path)))
        #expect(benchReportMarkdown.contains("# Melix Benchmark Report"))
        #expect(benchReportMarkdown.contains("| bench-1 | benchmark | melix-dev-text |"))
        #expect(benchReportMarkdown.contains("record_scan_ms="))
        #expect(benchReportMarkdown.contains("markdown_render_ms="))
        #expect(benchReportMarkdown.contains("eval-1") == false)

        let evalReportJSON = try await runner.run(.evalReport(.init(sourcePath: sourceRoot.path, format: "json")))
        let evalReportPayload = try #require(parseJSONObject(evalReportJSON))
        let generation = try #require(evalReportPayload["report_generation"] as? [String: Any])
        #expect(evalReportPayload["report_kind"] as? String == "evaluation")
        #expect(evalReportPayload["run_count"] as? Int == 1)
        #expect(generation["record_scan_ms"] != nil)
        #expect(generation["markdown_render_ms"] != nil)

        let systemJSON = try await runner.run(.system(.init(json: true)))
        let systemPayload = try #require(parseJSONObject(systemJSON))
        #expect(systemPayload["diagnostics_consent_state"] as? String == "local_only")
        #expect(systemPayload["redaction_schema_version"] as? String == MelixDiagnosticsRedaction.schemaVersion)
        #expect((systemPayload["redacted_field_count"] as? Int ?? 0) >= 1)

        let monitorJSON = try await runner.run(.monitor(.init(sourcePath: sourceRoot.path, json: true)))
        let monitorPayload = try #require(parseJSONObject(monitorJSON))
        let recentRuns = try #require(monitorPayload["recent_runs"] as? [[String: Any]])
        #expect(monitorPayload["run_count"] as? Int == 2)
        #expect(recentRuns.first?["run_id"] as? String == "bench-1")

        let logsText = try await runner.run(.logs(.init(jobID: "bench-1", sourcePath: sourceRoot.path, follow: true)))
        #expect(logsText.contains("benchmark failed after import"))
        #expect(logsText.contains("sk-secret-log") == false)
        #expect(logsText.contains("<redacted>"))

        let logsJSON = try await runner.run(.logs(.init(jobID: "bench-1", sourcePath: sourceRoot.path, follow: true, json: true)))
        let logsPayload = try #require(parseJSONObject(logsJSON))
        #expect(logsPayload["follow_requested"] as? Bool == true)
        #expect(logsPayload["active_follow_supported"] as? Bool == false)
        #expect((logsPayload["content"] as? String)?.contains("sk-secret-log") == false)

        try writeJSONObjectForTest(
            makeRunRecordPayloadForTest(
                runID: "eval-1",
                runKind: "evaluation",
                runRoot: evalRunRoot,
                startedAtUnixMS: 100,
                status: "running",
                metricName: "eval.mmlu.accuracy",
                metricUnit: "ratio"
            ),
            to: evalRunRoot.appendingPathComponent("run-record.json")
        )
        Task.detached {
            try? await Task.sleep(nanoseconds: 100_000_000)
            if let handle = try? FileHandle(forWritingTo: evalRunRoot.appendingPathComponent("logs.txt")) {
                try? handle.seekToEnd()
                try? handle.write(contentsOf: Data("active line 2\n".utf8))
                try? handle.close()
            }
        }
        let activeLogsJSON = try await runner.run(.logs(.init(jobID: "eval-1", sourcePath: sourceRoot.path, follow: true, json: true)))
        let activeLogsPayload = try #require(parseJSONObject(activeLogsJSON))
        #expect(activeLogsPayload["follow_requested"] as? Bool == true)
        #expect(activeLogsPayload["active_follow_supported"] as? Bool == true)
        #expect((activeLogsPayload["content"] as? String)?.contains("active line 2") == true)

        let bundleOutputRoot = root.appendingPathComponent("debug-output/bench-1", isDirectory: true)
        let bundleJSON = try await runner.run(
            .debugBundle(
                .init(
                    runID: "bench-1",
                    sourcePath: sourceRoot.path,
                    outputPath: bundleOutputRoot.path,
                    json: true
                )
            )
        )
        let bundlePayload = try #require(parseJSONObject(bundleJSON))
        #expect(bundlePayload["bundle_path"] as? String == bundleOutputRoot.path)
        #expect(bundlePayload["diagnostics_consent_state"] as? String == "local_only")
        for filename in [
            "command.txt",
            "redacted-env.json",
            "effective-config.json",
            "system.json",
            "capability-receipts.json",
            "memory-estimate.json",
            "logs.txt",
            "metrics.json",
            "error.json",
            "manifest.json",
        ] {
            #expect(FileManager.default.fileExists(atPath: bundleOutputRoot.appendingPathComponent(filename).path))
        }
        let bundleLogs = try String(contentsOf: bundleOutputRoot.appendingPathComponent("logs.txt"), encoding: .utf8)
        let bundleEnv = try String(contentsOf: bundleOutputRoot.appendingPathComponent("redacted-env.json"), encoding: .utf8)
        let bundleCommand = try String(contentsOf: bundleOutputRoot.appendingPathComponent("command.txt"), encoding: .utf8)
        let bundleConfig = try String(contentsOf: bundleOutputRoot.appendingPathComponent("effective-config.json"), encoding: .utf8)
        let bundleManifestData = try Data(contentsOf: bundleOutputRoot.appendingPathComponent("manifest.json"))
        let bundleManifest = try #require(
            JSONSerialization.jsonObject(with: bundleManifestData) as? [String: Any]
        )
        let probePolicy = try #require(bundleManifest["probe_policy"] as? [String: Any])
        #expect(bundleLogs.contains("sk-secret-log") == false)
        #expect(bundleEnv.contains("sk-secret-env") == false)
        #expect(bundleCommand.contains("hidden-prompt-token") == false)
        #expect(bundleConfig.contains("hidden-prompt-token") == false)
        #expect(bundleConfig.contains("sk-secret-header") == false)
        #expect(bundleConfig.contains("sk-secret-path") == false)
        #expect(bundleEnv.contains("<redacted:"))
        #expect(probePolicy["mode"] as? String == "debug")
        #expect(bundleManifest["debug_artifact_policy"] as? String == "explicit_cli_command")
        #expect(bundleManifest["debug_jsonl_enabled"] as? Bool == true)
        #expect(bundleManifest["debug_jsonl_event_limit"] as? Int == 256)

        let emptyList = try await runner.run(.runsList(.init(sourcePath: root.appendingPathComponent("missing").path)))
        #expect(emptyList == "No run records found.\n")

        do {
            _ = try await runner.run(.runsExport(.init(runID: "bench-1", sourcePath: sourceRoot.path, format: "txt")))
            Issue.record("Expected runs export to reject an unsupported format.")
        } catch let error as MelixCLIError {
            #expect(error == .usage("Invalid value for --format. Expected json or md."))
        }

        do {
            _ = try await runner.run(.benchReport(.init(sourcePath: sourceRoot.path, format: "txt")))
            Issue.record("Expected bench report to reject an unsupported format.")
        } catch let error as MelixCLIError {
            #expect(error == .usage("Invalid value for --format. Expected markdown or json."))
        }
    }

    @Test("run record store handles default roots invalid records and render fallbacks")
    func runRecordStoreHandlesDefaultRootsInvalidRecordsAndRenderFallbacks() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-run-record-store-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": root.path])
        let store = MelixRunRecordStore(melixHome: melixHome)
        let benchRunRoot = melixHome.modelOpsJobsRootURL
            .appendingPathComponent("bench", isDirectory: true)
            .appendingPathComponent("bench-a", isDirectory: true)
        let evalRunRoot = melixHome.evaluationJobsRootURL
            .appendingPathComponent("eval-a", isDirectory: true)
        try FileManager.default.createDirectory(at: benchRunRoot, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: evalRunRoot, withIntermediateDirectories: true)
        try writeJSONObjectForTest(
            makeRunRecordPayloadForTest(runID: "bench-a", runKind: "benchmark", runRoot: benchRunRoot, startedAtUnixMS: 10),
            to: benchRunRoot.appendingPathComponent("run-record.json")
        )
        let nestedArtifactRoot = benchRunRoot
            .appendingPathComponent("artifacts", isDirectory: true)
            .appendingPathComponent("checkpoint", isDirectory: true)
        try FileManager.default.createDirectory(at: nestedArtifactRoot, withIntermediateDirectories: true)
        try writeJSONObjectForTest(
            makeRunRecordPayloadForTest(
                runID: "nested-artifact",
                runKind: "benchmark",
                runRoot: nestedArtifactRoot,
                startedAtUnixMS: 30
            ),
            to: nestedArtifactRoot.appendingPathComponent("run-record.json")
        )
        try writeJSONObjectForTest(
            makeRunRecordPayloadForTest(runID: "eval-a", runKind: "evaluation", runRoot: evalRunRoot, startedAtUnixMS: 10),
            to: evalRunRoot.appendingPathComponent("run-record.json")
        )

        let defaultRecords = try store.loadRecords()
        #expect(defaultRecords.map(\.runID) == ["bench-a", "eval-a"])
        #expect(defaultRecords.contains { $0.runID == "nested-artifact" } == false)
        #expect(try store.report(kind: "runs", sourcePath: root.path).payload["run_count"] as? Int == 2)

        let invalidRoot = root.appendingPathComponent("invalid", isDirectory: true)
        try FileManager.default.createDirectory(at: invalidRoot, withIntermediateDirectories: true)
        try writeJSONObjectForTest(
            ["schema_version": "other", "run_id": "ignored"],
            to: invalidRoot.appendingPathComponent("run-record.json")
        )
        #expect(try store.loadRecords(sourcePath: invalidRoot.path).isEmpty)

        do {
            _ = try store.findRecord(runID: "missing", sourcePath: root.path)
            Issue.record("Expected missing run record lookup to fail.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("No run record was found for missing."))
        }

        #expect(MelixRunRecord(payload: [:], path: "").startedAtUnixMS == 0)
        let directRecord = MelixRunRecord(
            payload: [
                "run_id": "direct",
                "run_kind": "evaluation_compare",
                "status": "completed",
                "started_at_unix_ms": NSNumber(value: 42),
                "duration_ms": "7",
                "command": ["display": "melix eval compare --base-model-id base"],
                "environment": ["platform": "Darwin"],
                "target": [
                    "base_model_id": "base",
                    "task_kind": [1, "text-generation"],
                    "model_id": ["model-a", "model-b"],
                ],
                "dataset": [
                    "suite_ids": ["mmlu", "gsm8k"],
                    "dataset_ref": "dataset/ref",
                    "sample_size": ["2"],
                ],
                "metrics": [],
                "artifacts": [],
                "known_gaps": [],
                "artifact_root": "",
            ],
            path: "/tmp/run-record.json"
        )

        #expect(directRecord.startedAtUnixMS == 42)
        #expect(directRecord.durationMS == 7)
        #expect(renderRunRecordList([directRecord]).contains("model-a,model-b"))
        #expect(renderRunRecordMarkdown(directRecord).contains("- None."))
        #expect(renderRunRecordMarkdown(directRecord).contains("- None."))
        #expect(renderRunRecordMarkdown(directRecord).contains("No rows.") == false)
        #expect(renderReportMarkdown(["report_kind": "runs"]).contains("- None."))
        #expect(try writeRunRecordOutput("inline\n", outputPath: "") == "inline\n")
    }

    @Test("stub control-plane client covers auxiliary protocol helpers used by the CLI tests")
    func stubControlPlaneClientCoversAuxiliaryHelpers() async throws {
        let client = StubControlPlaneXPCClient()

        let handshake = try await client.handshake()
        let subscription = await client.subscribe(lastSeenSeq: 7)
        var iterator = subscription.makeAsyncIterator()
        let chat = try await client.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "hello")]
            )
        )
        let unloaded = try await client.unloadModel(modelID: "melix-dev-text")
        let updated = try await client.updateModelSettings(modelID: "melix-dev-text", values: ["alias": "Demo"])
        let info = try await client.modelInfo(modelID: "melix-dev-text")
        let generated = try await client.generateImage(
            .init(modelID: "melix-dev-image", prompt: "render")
        )
        let edited = try await client.editImage(
            .init(modelID: "melix-dev-image", prompt: "edit")
        )
        let doctor = try await client.runDoctor()
        let cancelled = try await client.cancelRequest(requestID: "request-1")
        try await client.applyServerSessionGatewayAccess(
            serverSessionID: "session-1",
            primaryKey: "pk",
            keyID: "key",
            label: "demo",
            tokenHint: "***"
        )
        try await client.clearServerSessionGatewayAccess(serverSessionID: "session-1")

        #expect(handshake.protocolVersion.isEmpty)
        #expect(await iterator.next() == nil)
        #expect(chat.requestID == "stub-chat")
        #expect(unloaded.modelID == "melix-dev-text")
        #expect(updated.modelID == "melix-dev-text")
        #expect(info.ok == false)
        #expect(generated.jobID.isEmpty)
        #expect(edited.jobID.isEmpty)
        #expect(doctor.markdown.isEmpty)
        #expect(doctor.findings.isEmpty)
        #expect(cancelled == false)
        #expect(parseJSONObject("not-json") == nil)
        #expect(parseJSONObject(#"{"ok":true}"#)?["ok"] as? Bool == true)
    }
}

@Suite("Phase 8 LoRA CLI Smoke", .serialized)
struct Phase8LoRACLISmokeTests {
    @Test("phase 8 lora cli smoke emits canonical acceptance evidence")
    func phase8LoRACLISmokeEmitsCanonicalAcceptanceEvidence() async throws {
        let baseModelID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        let derivedModelID = "melix-qwen35-acceptance"
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-phase8-lora-cli-smoke-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(models: [
            makeModelSummary(id: baseModelID, kind: "text"),
            makeModelSummary(id: derivedModelID, kind: "text"),
        ]))
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))
        let runner = MelixCLIRunner(client: client)

        await client.setModelOperationResult(
            makeModelOperationResult(outputPath: "/tmp/melix/train_lora/train-job-1")
        )
        let trainOutput = try await runSmokeCLICommand(
            [
                "lora", "train",
                "--model-id", baseModelID,
                "--hf-dataset-path", "HuggingFaceH4/ultrachat_200k",
                "--hf-train-split", "train_sft",
                "--chat-feature", "messages",
                "--adapter-name", "qwen35-acceptance",
                "--training-mode", "qlora",
                "--derived-model-alias", derivedModelID,
                "--json",
            ],
            runner: runner
        )
        let trainPayload = try #require(parseJSONObject(trainOutput))
        let trainCall = try #require(await client.lastModelOperationCall)

        await client.setModelOperationResult(
            makeModelOperationResult(outputPath: "/tmp/melix/activate_adapter/activate-job-1")
        )
        let activateOutput = try await runSmokeCLICommand(
            [
                "lora", "activate",
                "--model-id", baseModelID,
                "--adapter-path", "/tmp/melix/train_lora/train-job-1/train_lora.adapter.json",
                "--activation-mode", "adapter_backed_runtime",
                "--alias", derivedModelID,
                "--json",
            ],
            runner: runner
        )
        let activatePayload = try #require(parseJSONObject(activateOutput))
        let activateCall = try #require(await client.lastModelOperationCall)

        await client.setEvaluationResults([
            makeEvaluationCompareResult(
                jobID: "eval-compare-1",
                baseSuiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                targets: [(derivedModelID, 0.625)]
            ),
        ])
        let compareOutput = try await runSmokeCLICommand(
            [
                "eval", "compare",
                "--model-id", baseModelID,
                "--target-model-id", derivedModelID,
                "--suite", "mmlu",
                "--sample-size", "6",
                "--batch-factor", "2",
                "--few-shot", "1",
                "--seed", "9",
                "--scoring-mode", "multiple_choice_accuracy",
                "--code-exec-policy", "sandboxed",
                "--json",
            ],
            runner: runner
        )
        let comparePayload = try #require(parseJSONArray(compareOutput))
        let compareEntry = try #require(comparePayload.first as? [String: Any])
        let compareJob = try #require(compareEntry["job"] as? [String: Any])
        let compareRequest = try #require((await client.evaluationRequests).last)

        let summaryURL = root.appendingPathComponent("eval-1-summary.csv")
        let exportOutput = try await runSmokeCLICommand(
            [
                "eval", "export-summary-csv",
                "--job-id", "eval-1",
                "--output", summaryURL.path,
                "--json",
            ],
            runner: runner
        )
        let exportPayload = try #require(parseJSONObject(exportOutput))
        let exportCSV = try String(contentsOf: summaryURL, encoding: .utf8)

        await client.setModelOperationResult(
            makeModelOperationResult(outputPath: "/tmp/melix/remove_derived_model/remove-job-1")
        )
        let removeOutput = try await runSmokeCLICommand(
            [
                "lora", "remove-derived",
                "--model-id", baseModelID,
                "--derived-model-id", derivedModelID,
                "--json",
            ],
            runner: runner
        )
        let removePayload = try #require(parseJSONObject(removeOutput))
        let removeCall = try #require(await client.lastModelOperationCall)

        let negativePayload: [String: String] = [
            "train_missing_adapter_name": try captureSmokeCLIError(
                ["lora", "train", "--model-id", baseModelID, "--dataset-uri", "datasets/melix-dev"]
            ),
            "activate_missing_adapter_path": try captureSmokeCLIError(
                ["lora", "activate", "--model-id", baseModelID]
            ),
            "compare_missing_target": try captureSmokeCLIError(
                ["eval", "compare", "--model-id", baseModelID]
            ),
            "export_missing_job": try await captureSmokeRunnerError(
                [
                    "eval", "export-summary-csv",
                    "--job-id", "eval-missing",
                    "--output", root.appendingPathComponent("eval-missing.csv").path,
                ],
                runner: runner
            ),
            "remove_missing_target": try captureSmokeCLIError(
                ["lora", "remove-derived", "--model-id", baseModelID]
            ),
        ]

        let positiveTrain: [String: Any] = [
            "job_id": trainPayload["job_id"] as? String ?? "train-job-1",
            "output_path": trainPayload["output_path"] as? String ?? "",
            "training_mode": trainCall.ext["training_mode"] ?? "",
        ]
        let positiveActivate: [String: Any] = [
            "job_id": activatePayload["job_id"] as? String ?? "activate-job-1",
            "output_path": activatePayload["output_path"] as? String ?? "",
            "activation_mode": activateCall.ext["activation_mode"] ?? "",
        ]
        let positiveCompare: [String: Any] = [
            "job_id": compareJob["job_id"] as? String ?? "",
            "target_model_ids": [derivedModelID],
            "metric": "eval.compare.win_rate",
            "compare_mode": compareRequest.parameters["compare_mode"] ?? "",
        ]
        let positiveExport: [String: Any] = [
            "job_id": exportPayload["job_id"] as? String ?? "",
            "output_path": summaryURL.path,
            "row_count": exportPayload["row_count"] as? Int ?? 0,
        ]
        let positiveRemove: [String: Any] = [
            "job_id": removePayload["job_id"] as? String ?? "remove-job-1",
            "output_path": removePayload["output_path"] as? String ?? "",
            "derived_model_id": removeCall.ext["derived_model_id"] ?? "",
        ]
        let positivePayload: [String: Any] = [
            "train": positiveTrain,
            "activate": positiveActivate,
            "compare": positiveCompare,
            "export": positiveExport,
            "remove_derived": positiveRemove,
        ]
        let payload: [String: Any] = [
            "model_id": baseModelID,
            "positive": positivePayload,
            "negative": negativePayload,
        ]
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
        print("PHASE8_LORA_CLI_SMOKE=\(String(decoding: data, as: UTF8.self))")

        #expect(trainCall.operation == "train_lora")
        #expect(trainCall.ext["training_mode"] == "qlora")
        #expect(activateCall.operation == "activate_adapter")
        #expect(activateCall.ext["activation_mode"] == "adapter_backed_runtime")
        #expect(compareRequest.parameters["compare_target_model_ids"] == derivedModelID)
        #expect(exportPayload["row_count"] as? Int == 1)
        #expect(exportCSV.contains("eval-1"))
        #expect(removeCall.operation == "remove_derived_model")
        #expect(removeCall.ext["derived_model_id"] == derivedModelID)
        #expect(negativePayload["export_missing_job"] == "No evaluation rows were found for job eval-missing.")
    }
}

private final class EnvironmentRecorder: @unchecked Sendable {
    private(set) var environment: [String: String]?

    func record(_ environment: [String: String]) {
        self.environment = environment
    }
}

private func requireUsageError(_ body: () async throws -> Void) async throws -> String {
    do {
        try await body()
        Issue.record("Expected MelixCLIError.usage to be thrown.")
        return ""
    } catch let error as MelixCLIError {
        guard case .usage(let message) = error else {
            Issue.record("Expected MelixCLIError.usage, got \(error).")
            return ""
        }
        return message
    } catch {
        Issue.record("Expected MelixCLIError.usage, got \(error).")
        return ""
    }
}

private func requireRuntimeError(_ body: () async throws -> Void) async throws -> String {
    do {
        try await body()
        Issue.record("Expected MelixCLIError.runtime to be thrown.")
        return ""
    } catch let error as MelixCLIError {
        guard case .runtime(let message) = error else {
            Issue.record("Expected MelixCLIError.runtime, got \(error).")
            return ""
        }
        return message
    } catch {
        Issue.record("Expected MelixCLIError.runtime, got \(error).")
        return ""
    }
}

private actor ExportResultsOnlyControlPlaneService: ControlPlaneExecuting {
    private let exportBundleJSON: String

    init(exportBundleJSON: String) {
        self.exportBundleJSON = exportBundleJSON
    }

    func handshake(
        _ request: Melix_Controlplane_V1_HandshakeRequest
    ) async throws -> Melix_Controlplane_V1_HandshakeResponse {
        _ = request
        return Melix_Controlplane_V1_HandshakeResponse()
    }

    func subscribe(
        _ request: Melix_Controlplane_V1_SubscribeRequest
    ) async -> ControlPlaneSubscription {
        _ = request
        return ControlPlaneSubscription(
            subscriptionID: "sub-export-only",
            stream: AsyncStream { continuation in
                continuation.finish()
            }
        )
    }

    func unsubscribe(_ subscriptionID: String) async {
        _ = subscriptionID
    }

    func startChat(
        _ request: ControlPlaneChatRequest
    ) async throws -> ControlPlaneChatExecution {
        _ = request
        return ControlPlaneChatExecution(
            requestID: "export-only-chat",
            modelID: "melix-dev-text",
            stream: AsyncThrowingStream { continuation in
                continuation.finish()
            }
        )
    }

    func execute(
        _ request: Melix_Controlplane_V1_ControlPlaneRequest
    ) async throws -> Melix_Controlplane_V1_ControlPlaneResponse {
        guard case .ops(let command) = request.command,
              case .exportResults = command.kind
        else {
            Issue.record("Unexpected control-plane command for export-only CLI service.")
            return Melix_Controlplane_V1_ControlPlaneResponse()
        }

        var response = Melix_Controlplane_V1_ControlPlaneResponse()
        response.requestID = request.requestID
        response.commandType = request.commandType
        response.ok = true
        response.ops.exportBundleJson = exportBundleJSON
        return response
    }
}

private actor RecordingCLICommandExecutor {
    private let responses: [String]
    private var responseIndex = 0
    private(set) var commands: [[String]] = []

    init(responses: [String]) {
        self.responses = responses
    }

    func run(_ arguments: [String]) async throws -> String {
        commands.append(arguments)
        guard responseIndex < responses.count else {
            throw MelixCLIError.runtime("No subprocess response was configured for \(arguments.joined(separator: " ")).")
        }
        let response = responses[responseIndex]
        responseIndex += 1
        return response
    }
}

private func runSmokeCLICommand(
    _ arguments: [String],
    runner: MelixCLIRunner
) async throws -> String {
    let command = try MelixCLIParser.parse(arguments)
    return try await runner.run(command)
}

private func captureSmokeCLIError(_ arguments: [String]) throws -> String {
    do {
        _ = try MelixCLIParser.parse(arguments)
        Issue.record("Expected parser failure for arguments: \(arguments)")
    } catch let error as MelixCLIError {
        return error.localizedDescription
    }
    return ""
}

private func captureSmokeRunnerError(
    _ arguments: [String],
    runner: MelixCLIRunner
) async throws -> String {
    do {
        _ = try await runSmokeCLICommand(arguments, runner: runner)
        Issue.record("Expected runner failure for arguments: \(arguments)")
    } catch let error as MelixCLIError {
        return error.localizedDescription
    }
    return ""
}

private func posixPermissions(at url: URL) throws -> Int {
    let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
    return (attributes[.posixPermissions] as? NSNumber)?.intValue ?? 0
}

private actor StubControlPlaneXPCClient: ControlPlaneXPCClient {
    enum ServerAction: Sendable, Equatable {
        case start(String)
        case pause(String)
        case resume(String)
        case wake(String)
        case stop(String)
    }

    struct IdlePolicyCall: Sendable, Equatable {
        let serverSessionID: String
        let autoSleepEnabled: Bool
        let lightSleepAfterSeconds: UInt32
        let deepSleepAfterSeconds: UInt32
    }

    struct ModelOperationCall: Sendable, Equatable {
        let modelID: String
        let operation: String
        let outputDir: String
        let quantProfileID: String
        let weightQuant: String
        let kvQuant: String
        let ext: [String: String]
    }

    struct GatewayConfigApplyCall: Sendable, Equatable {
        let serverSessionID: String
        let host: String
        let port: Int
        let defaultModelID: String
        let servedModelIDs: [String]
        let rateLimitPerMinute: Int
        let timeoutSeconds: Int
        let modelIdleTimeoutSeconds: Int
    }

    struct ServingDefaultsApplyCall: Sendable, Equatable {
        let serverSessionID: String
        let temperature: Double
        let topP: Double
        let maxTokens: Int
        let streamIntervalTokens: Int
        let maxConcurrentRequests: Int
        let concurrentProcessingEnabled: Bool
        let prefillBatchSize: Int
        let completionBatchSize: Int
        let accelerationMode: Melix_Controlplane_V1_AccelerationMode
        let draftModelID: String
        let numDraftTokens: Int
    }

    private(set) var lastServerAction: ServerAction?
    private(set) var lastIdlePolicyCall: IdlePolicyCall?
    private(set) var lastModelOperationCall: ModelOperationCall?
    private(set) var lastChatRequest: ControlPlaneChatRequest?
    private(set) var lastGatewayConfigApplyRequest: GatewayConfigApplyCall?
    private(set) var lastServingDefaultsApplyRequest: ServingDefaultsApplyCall?
    private(set) var lastBenchRequest: ControlPlaneBenchRequest?
    private(set) var lastBenchMatrixRequest: ControlPlaneBenchMatrixRequest?
    private(set) var lastHubModelCardRepoID: String?
    private(set) var evaluationRequests: [ControlPlaneEvaluationRequest] = []
    private(set) var loadedModelIDs: [String] = []

    private var snapshot = makeServerSnapshot(models: [makeModelSummary(id: "melix-dev-text", kind: "text")])
    private var modelOperationResult = makeModelOperationResult()
    private var modelOperationResultsByOperation: [String: Melix_Controlplane_V1_ModelOperationResult] = [:]
    private(set) var modelOperationCalls: [ModelOperationCall] = []
    private var benchResult = ControlPlaneBenchResult(reportPath: "", reportMarkdown: "", metrics: [:])
    private var benchMatrixResult = ControlPlaneBenchMatrixResult(
        job: makeBenchmarkMatrixJobSummary(jobID: "", modelID: "", taskKind: "", sourceRepo: ""),
        summaryRows: []
    )
    private var hubSearchResult = Melix_Controlplane_V1_HubSearchResult()
    private var hubModelCard = Melix_Controlplane_V1_HubModelCard()
    private var doctorReport = makeDoctorReport()
    private var evaluationResultsQueue: [ControlPlaneEvaluationResult] = []
    private var evaluationResultsByRemoteModelID: [String: ControlPlaneEvaluationResult] = [:]
    private var evaluationDelayNanoseconds: UInt64 = 0
    private var activeEvaluationCalls = 0
    private(set) var maxConcurrentEvaluationCalls = 0
    private var exportResult = ControlPlaneExportResult(exportBundleJSON: #"{"export_schema_version":"melix.benchmark_export.v1","benchmark_jobs":[],"benchmark_results":[]}"#)
    private var modelInfoByID: [String: Melix_Controlplane_V1_ModelInfo] = [:]
    private var loadError: Error?
    private var modelOperationError: Error?
    private var chatError: Error?
    private var chatRequestID = "stub-chat"
    private var chatModelID = "melix-dev-text"
    private var chatEvents: [ControlPlaneChatStreamEvent] = []

    func setServerSnapshot(_ snapshot: Melix_Controlplane_V1_ServerSnapshot) {
        self.snapshot = snapshot
    }

    func setModelOperationResult(_ result: Melix_Controlplane_V1_ModelOperationResult) {
        self.modelOperationResult = result
    }

    func setModelOperationResult(
        _ result: Melix_Controlplane_V1_ModelOperationResult,
        forOperation operation: String
    ) {
        modelOperationResultsByOperation[operation] = result
    }

    func setModelOperationError(_ error: Error?) {
        self.modelOperationError = error
    }

    func setChatError(_ error: Error?) {
        self.chatError = error
    }

    func setBenchResult(_ result: ControlPlaneBenchResult) {
        self.benchResult = result
    }

    func setBenchMatrixResult(_ result: ControlPlaneBenchMatrixResult) {
        self.benchMatrixResult = result
    }

    func setHubSearchResult(_ result: Melix_Controlplane_V1_HubSearchResult) {
        self.hubSearchResult = result
    }

    func setHubModelCard(_ card: Melix_Controlplane_V1_HubModelCard) {
        self.hubModelCard = card
    }

    func setDoctorReport(_ report: Melix_Controlplane_V1_DoctorReport) {
        doctorReport = report
    }

    func setEvaluationResults(_ results: [ControlPlaneEvaluationResult]) {
        self.evaluationResultsQueue = results
    }

    func setEvaluationResultsByRemoteModelID(_ results: [String: ControlPlaneEvaluationResult]) {
        self.evaluationResultsByRemoteModelID = results
    }

    func setEvaluationDelay(nanoseconds: UInt64) {
        self.evaluationDelayNanoseconds = nanoseconds
    }

    func setExportResult(_ result: ControlPlaneExportResult) {
        self.exportResult = result
    }

    func setModelInfo(modelID: String, info: Melix_Controlplane_V1_ModelInfo) {
        modelInfoByID[modelID] = info
    }

    func setLoadError(_ error: Error?) {
        loadError = error
    }

    func setChatExecution(
        requestID: String,
        modelID: String,
        events: [ControlPlaneChatStreamEvent]
    ) {
        self.chatRequestID = requestID
        self.chatModelID = modelID
        self.chatEvents = events
    }

    func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse {
        Melix_Controlplane_V1_HandshakeResponse()
    }

    func subscribe(lastSeenSeq: UInt64) async -> AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent> {
        _ = lastSeenSeq
        return AsyncStream { continuation in
            continuation.finish()
        }
    }

    func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution {
        lastChatRequest = request
        if let chatError {
            throw chatError
        }
        let events = chatEvents
        return ControlPlaneChatExecution(
            requestID: chatRequestID,
            modelID: chatModelID,
            stream: AsyncThrowingStream { continuation in
                for event in events {
                    continuation.yield(event)
                }
                continuation.finish()
            }
        )
    }

    func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot {
        snapshot
    }

    func startServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        lastServerAction = .start(serverSessionID)
        mutateRuntimeSession(serverSessionID: serverSessionID) { session in
            session.lifecycleState = .ready
            session.powerState = .active
            session.wakeReason = .operatorResume
        }
        snapshot.serverState = .serverReady
        return snapshot
    }

    func pauseServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        lastServerAction = .pause(serverSessionID)
        mutateRuntimeSession(serverSessionID: serverSessionID) { session in
            session.lifecycleState = .paused
            session.powerState = .active
        }
        snapshot.serverState = .serverDegraded
        return snapshot
    }

    func resumeServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        lastServerAction = .resume(serverSessionID)
        mutateRuntimeSession(serverSessionID: serverSessionID) { session in
            session.lifecycleState = .ready
            session.powerState = .active
            session.wakeReason = .operatorResume
        }
        snapshot.serverState = .serverReady
        return snapshot
    }

    func wakeServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        lastServerAction = .wake(serverSessionID)
        mutateRuntimeSession(serverSessionID: serverSessionID) { session in
            session.lifecycleState = .ready
            session.powerState = .active
            session.wakeReason = .requestActivity
        }
        snapshot.serverState = .serverReady
        return snapshot
    }

    func stopServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        lastServerAction = .stop(serverSessionID)
        mutateRuntimeSession(serverSessionID: serverSessionID) { session in
            session.lifecycleState = .stopped
            session.powerState = .stopped
        }
        snapshot.serverState = .serverStopped
        return snapshot
    }

    func updateServerIdlePolicy(
        serverSessionID: String,
        autoSleepEnabled: Bool,
        lightSleepAfterSeconds: UInt32,
        deepSleepAfterSeconds: UInt32
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        lastIdlePolicyCall = IdlePolicyCall(
            serverSessionID: serverSessionID,
            autoSleepEnabled: autoSleepEnabled,
            lightSleepAfterSeconds: lightSleepAfterSeconds,
            deepSleepAfterSeconds: deepSleepAfterSeconds
        )
        mutateRuntimeSession(serverSessionID: serverSessionID) { session in
            session.autoSleepEnabled = autoSleepEnabled
            session.lightSleepAfterSeconds = lightSleepAfterSeconds
            session.deepSleepAfterSeconds = deepSleepAfterSeconds
        }
        return snapshot
    }

    func loadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        if let loadError {
            throw loadError
        }
        loadedModelIDs.append(modelID)
        return makeModelSummary(id: modelID, kind: "text")
    }

    func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        makeModelSummary(id: modelID, kind: "text")
    }

    func updateModelSettings(
        modelID: String,
        values: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelSummary {
        _ = values
        return makeModelSummary(id: modelID, kind: "text")
    }

    func modelInfo(modelID: String) async throws -> Melix_Controlplane_V1_ModelInfo {
        modelInfoByID[modelID] ?? Melix_Controlplane_V1_ModelInfo()
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
        if let modelOperationError {
            throw modelOperationError
        }
        let call = ModelOperationCall(
            modelID: modelID,
            operation: operation,
            outputDir: outputDir,
            quantProfileID: quantProfileID,
            weightQuant: weightQuant,
            kvQuant: kvQuant,
            ext: ext
        )
        lastModelOperationCall = call
        modelOperationCalls.append(call)
        if let perOperation = modelOperationResultsByOperation[operation] {
            return perOperation
        }
        return modelOperationResult
    }

    func searchHubModels(
        query: String,
        pageSize: UInt32,
        cursor: String,
        mlxOnly: Bool
    ) async throws -> Melix_Controlplane_V1_HubSearchResult {
        _ = query
        _ = pageSize
        _ = cursor
        _ = mlxOnly
        return hubSearchResult
    }

    func getHubModelCard(repoID: String) async throws -> Melix_Controlplane_V1_HubModelCard {
        lastHubModelCardRepoID = repoID
        return hubModelCard
    }

    func generateImage(
        _ request: ControlPlaneImageGenerationRequest
    ) async throws -> Melix_Controlplane_V1_ImageJobSummary {
        _ = request
        return Melix_Controlplane_V1_ImageJobSummary()
    }

    func editImage(
        _ request: ControlPlaneImageEditRequest
    ) async throws -> Melix_Controlplane_V1_ImageJobSummary {
        _ = request
        return Melix_Controlplane_V1_ImageJobSummary()
    }

    func runDoctor() async throws -> Melix_Controlplane_V1_DoctorReport {
        doctorReport
    }

    func runBench(_ request: ControlPlaneBenchRequest) async throws -> ControlPlaneBenchResult {
        lastBenchRequest = request
        return benchResult
    }

    func runBenchMatrix(_ request: ControlPlaneBenchMatrixRequest) async throws -> ControlPlaneBenchMatrixResult {
        lastBenchMatrixRequest = request
        return benchMatrixResult
    }

    func runEvaluation(_ request: ControlPlaneEvaluationRequest) async throws -> ControlPlaneEvaluationResult {
        evaluationRequests.append(request)
        activeEvaluationCalls += 1
        maxConcurrentEvaluationCalls = max(maxConcurrentEvaluationCalls, activeEvaluationCalls)
        defer {
            activeEvaluationCalls -= 1
        }
        if evaluationDelayNanoseconds > 0 {
            try await Task.sleep(nanoseconds: evaluationDelayNanoseconds)
        }
        let remoteModelID = request.remoteTarget?.modelID ?? ""
        if let result = evaluationResultsByRemoteModelID[remoteModelID] {
            return result
        }
        guard evaluationResultsQueue.isEmpty == false else {
            throw MelixCLIError.runtime("No stub evaluation result is configured.")
        }
        return evaluationResultsQueue.removeFirst()
    }

    func exportResults(outputDir: String) async throws -> ControlPlaneExportResult {
        _ = outputDir
        return exportResult
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

    func applyServerSessionGatewayConfig(
        serverSessionID: String,
        host: String,
        port: Int,
        defaultModelID: String,
        servedModelIDs: [String],
        rateLimitPerMinute: Int,
        timeoutSeconds: Int,
        modelIdleTimeoutSeconds: Int
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        lastGatewayConfigApplyRequest = GatewayConfigApplyCall(
            serverSessionID: serverSessionID,
            host: host,
            port: port,
            defaultModelID: defaultModelID,
            servedModelIDs: servedModelIDs,
            rateLimitPerMinute: rateLimitPerMinute,
            timeoutSeconds: timeoutSeconds,
            modelIdleTimeoutSeconds: modelIdleTimeoutSeconds
        )
        return snapshot
    }

    func applyServerSessionServingDefaults(
        serverSessionID: String,
        temperature: Double,
        topP: Double,
        maxTokens: Int,
        streamIntervalTokens: Int,
        maxConcurrentRequests: Int,
        concurrentProcessingEnabled: Bool,
        prefillBatchSize: Int,
        completionBatchSize: Int,
        accelerationMode: Melix_Controlplane_V1_AccelerationMode,
        draftModelID: String,
        numDraftTokens: Int
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        lastServingDefaultsApplyRequest = ServingDefaultsApplyCall(
            serverSessionID: serverSessionID,
            temperature: temperature,
            topP: topP,
            maxTokens: maxTokens,
            streamIntervalTokens: streamIntervalTokens,
            maxConcurrentRequests: maxConcurrentRequests,
            concurrentProcessingEnabled: concurrentProcessingEnabled,
            prefillBatchSize: prefillBatchSize,
            completionBatchSize: completionBatchSize,
            accelerationMode: accelerationMode,
            draftModelID: draftModelID,
            numDraftTokens: numDraftTokens
        )
        return snapshot
    }

    private func mutateRuntimeSession(
        serverSessionID: String,
        update: (inout Melix_Controlplane_V1_ServerSessionRuntimeState) -> Void
    ) {
        if let index = snapshot.runtimeSessions.firstIndex(where: { $0.serverSessionID == serverSessionID }) {
            update(&snapshot.runtimeSessions[index])
            return
        }

        var session = makeRuntimeSession(serverSessionID: serverSessionID)
        update(&session)
        snapshot.runtimeSessions.append(session)
    }
}

private func makeServerSnapshot(
    models: [Melix_Controlplane_V1_ModelSummary] = [],
    runtimeSessions: [Melix_Controlplane_V1_ServerSessionRuntimeState] = []
) -> Melix_Controlplane_V1_ServerSnapshot {
    var snapshot = Melix_Controlplane_V1_ServerSnapshot()
    snapshot.serverState = runtimeSessions.contains(where: { $0.lifecycleState == .paused || $0.lifecycleState == .sleeping })
        ? .serverDegraded
        : (runtimeSessions.allSatisfy { $0.lifecycleState == .stopped } && !runtimeSessions.isEmpty ? .serverStopped : .serverReady)
    snapshot.models = models
    snapshot.runtimeSessions = runtimeSessions
    return snapshot
}

private func makeRuntimeSession(
    serverSessionID: String = "server-session-1"
) -> Melix_Controlplane_V1_ServerSessionRuntimeState {
    var session = Melix_Controlplane_V1_ServerSessionRuntimeState()
    session.serverSessionID = serverSessionID
    session.lifecycleState = .ready
    session.powerState = .active
    session.wakeReason = .initialBoot
    session.updatedAtUnixMs = 1_234
    return session
}

private func makeModelSummary(
    id: String,
    kind: String,
    runtimeMode: String = "",
    activationMode: String = ""
) -> Melix_Controlplane_V1_ModelSummary {
    var model = Melix_Controlplane_V1_ModelSummary()
    model.modelID = id
    model.kind = kind
    model.runtimeMode = runtimeMode
    if !activationMode.isEmpty {
        model.settings.ext["melix.activation_mode"] = activationMode
    }
    return model
}

private func makeHubModelCard(
    repoID: String,
    localFitStatus: String,
    localFitReasons: [String],
    estimatedArtifactBytes: UInt64,
    estimatedResidentBytes: UInt64,
    recommendedAction: String,
    pipelineTag: String = "text-generation",
    mlxCompatible: Bool = true,
    parameterCount: UInt64 = 0,
    quantizationSummary: String = ""
) -> Melix_Controlplane_V1_HubModelCard {
    var card = Melix_Controlplane_V1_HubModelCard()
    card.repoID = repoID
    card.author = repoID.split(separator: "/").first.map(String.init) ?? ""
    card.modelName = repoID.split(separator: "/").dropFirst().first.map(String.init) ?? repoID
    card.pipelineTag = pipelineTag
    card.mlxCompatible = mlxCompatible
    card.localFitStatus = localFitStatus
    card.localFitReasons = localFitReasons
    card.estimatedArtifactBytes = estimatedArtifactBytes
    card.estimatedResidentBytes = estimatedResidentBytes
    card.recommendedAction = recommendedAction
    card.parameterCount = parameterCount
    card.quantizationSummary = quantizationSummary
    return card
}

private func makeModelOperationResult(
    outputPath: String = "",
    manifestJSON: String = #"{"adapters":[]}"#
) -> Melix_Controlplane_V1_ModelOperationResult {
    var result = Melix_Controlplane_V1_ModelOperationResult()
    result.outputPath = outputPath
    result.manifestJson = manifestJSON
    return result
}

private func makeDoctorReport(
    markdown: String = "",
    healthStatus: Melix_Controlplane_V1_DoctorHealthStatus = .unspecified,
    findings: [(code: String, severity: Melix_Controlplane_V1_DoctorHealthStatus, summary: String, detail: String)] = []
) -> Melix_Controlplane_V1_DoctorReport {
    var report = Melix_Controlplane_V1_DoctorReport()
    report.markdown = markdown
    report.healthStatus = healthStatus
    report.findings = findings.map { finding in
        var item = Melix_Controlplane_V1_DoctorFinding()
        item.code = finding.code
        item.severity = finding.severity
        item.summary = finding.summary
        item.detail = finding.detail
        return item
    }
    return report
}

private func makePublishesRegistryManifest() -> String {
    #"""
    {
      "operation": "registry_snapshot",
      "adapters": [],
      "derived_models": [],
      "publishes": [
        {
          "job_id": "model-ops-0100",
          "status": "published",
          "target_repo": "melix/adapters/adapter-a",
          "published_url": "https://huggingface.co/melix/adapters/adapter-a",
          "published_ref": "main",
          "published_files": ["train_lora.adapter.json", "adapter/adapters.safetensors", "adapter/adapter_config.json"],
          "publish_backend": "huggingface_hub",
          "export_artifact_kind": "adapter_export",
          "source_artifact_kind": "adapter",
          "distribution_contract": "adapter_only",
          "source_job_id": "model-ops-0050",
          "source_artifact_path": "/tmp/train-a/train_lora.adapter.json",
          "source_manifest_path": "/tmp/train-a/train_lora.adapter.json",
          "source_model": "melix-dev-text",
          "adapter_name": "adapter-a",
          "derived_model_id": "",
          "activation_mode": "",
          "parent_lineage": {"source_job_id": "model-ops-0050"},
          "receipt_path": "/tmp/upload-adapter/upload.receipt.json",
          "upload_duration_ms": 120.5
        },
        {
          "job_id": "model-ops-0101",
          "status": "published",
          "target_repo": "melix/models/melix-dev-fused",
          "published_url": "https://huggingface.co/melix/models/melix-dev-fused",
          "published_ref": "main",
          "published_files": ["manifest.json", "config.json", "weights/model-00001-of-00001.safetensors"],
          "publish_backend": "huggingface_hub",
          "export_artifact_kind": "merged_export",
          "source_artifact_kind": "derived_text_model",
          "distribution_contract": "merged_model",
          "source_job_id": "model-ops-0080",
          "source_artifact_path": "/runtime/activate/melix-dev-fused",
          "source_manifest_path": "/runtime/activate/melix-dev-fused/manifest.json",
          "source_model": "melix-dev-text",
          "adapter_name": "",
          "derived_model_id": "melix-dev-fused",
          "activation_mode": "fused_derived_model",
          "parent_lineage": {"source_job_id": "model-ops-0080", "derived_model_id": "melix-dev-fused"},
          "receipt_path": "/runtime/upload/upload.receipt.json",
          "upload_duration_ms": 321.0
        }
      ]
    }
    """#
}

private func makeExperimentsRegistryManifestWithoutBestLoss() -> String {
    #"""
    {
      "operation": "registry_snapshot",
      "adapters": [],
      "derived_models": [],
      "experiment_groups": [
        {
          "group_id": "cold-start",
          "title": "Cold Start",
          "adapter_name": "cold-start-adapter",
          "source_model": "melix-dev-text",
          "run_count": 1,
          "latest_preset_title": "Debug Fast",
          "resume_ready_run_ids": [],
          "checkpoint_lineage": [
            {"run_id": "model-ops-9999", "checkpoint_count": 0, "resume_ready": false}
          ]
        }
      ]
    }
    """#
}

private func makeExperimentsRegistryManifest(
    bestManifestPath: String = "/tmp/melix-train-lora/model-ops-0012/train_lora.adapter.json"
) -> String {
    #"""
    {
      "operation": "registry_snapshot",
      "adapters": [],
      "derived_models": [],
      "experiment_groups": [
        {
          "group_id": "nightly-qwen35",
          "title": "Nightly Qwen35",
          "adapter_name": "nightly-qwen35",
          "source_model": "melix-dev-text",
          "run_count": 3,
          "latest_run_id": "model-ops-0012",
          "latest_status": "activated",
          "latest_dataset_uri": "/tmp/datasets/nightly.jsonl",
          "latest_preset_id": "balanced_adapter",
          "latest_preset_title": "Balanced Adapter",
          "latest_tokens_per_second": 128.5,
          "latest_peak_memory_gb": 5.25,
          "latest_checkpoint_count": 5,
          "latest_resume_ready": true,
          "resume_ready_run_ids": ["model-ops-0012", "model-ops-0009"],
          "checkpoint_lineage": [
            { "run_id": "model-ops-0012", "checkpoint_count": 5, "resume_ready": true },
            { "run_id": "model-ops-0009", "checkpoint_count": 3, "resume_ready": true },
            { "run_id": "model-ops-0007", "checkpoint_count": 1, "resume_ready": false }
          ],
          "best_run_id": "model-ops-0012",
          "best_loss": 0.3287,
          "recommended_manifest_path": "\#(bestManifestPath)",
          "best_known_adapter": {
            "run_id": "model-ops-0012",
            "manifest_path": "\#(bestManifestPath)",
            "adapter_name": "nightly-qwen35",
            "checkpoint_count": 5,
            "latest_checkpoint_path": "/tmp/melix-train-lora/model-ops-0012/checkpoint",
            "resume_ready": true,
            "loss_best": 0.3287
          }
        }
      ]
    }
    """#
}

private func parseJSONObject(_ text: String) -> [String: Any]? {
    guard let data = text.data(using: .utf8) else {
        return nil
    }
    return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
}

private func writeJSONObjectForTest(_ object: [String: Any], to url: URL) throws {
    let data = try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys])
    try data.write(to: url)
}

private func parseJSONArray(_ text: String) -> [Any]? {
    guard let data = text.data(using: .utf8) else {
        return nil
    }
    return (try? JSONSerialization.jsonObject(with: data)) as? [Any]
}

private func parseJSONFile(_ path: String) throws -> [String: Any]? {
    let data = try Data(contentsOf: URL(fileURLWithPath: path))
    return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
}

private func makeRunRecordPayloadForTest(
    runID: String,
    runKind: String,
    runRoot: URL,
    startedAtUnixMS: Int,
    status: String = "completed",
    command: String? = nil,
    parameters: [String: Any] = [
        "sample_size": "2",
    ],
    metricName: String = "bench.smoke.ttft_ms",
    metricUnit: String = "ms"
) -> [String: Any] {
    let evaluation = runKind.hasPrefix("evaluation")
    let suiteID = evaluation ? "mmlu" : "smoke"
    let datasetID = evaluation ? "mmlu.dev.v1" : "ultrachat.smoke"
    let defaultCommand = evaluation
        ? "melix eval run --model-id melix-dev-text --suite mmlu --dataset-id mmlu.dev.v1 --sample-size 2"
        : "melix bench run --model-id melix-dev-text --suite smoke --sample-size 2"
    let command = command ?? defaultCommand
    return [
        "schema_version": "melix.run_record.v1",
        "run_id": runID,
        "run_kind": runKind,
        "status": status,
        "started_at_unix_ms": startedAtUnixMS,
        "ended_at_unix_ms": startedAtUnixMS + 50,
        "duration_ms": 50,
        "command": [
            "argv": command.split(separator: " ").map(String.init),
            "display": command,
            "redacted": false,
        ],
        "melix": [
            "git_commit": "abcdef",
            "git_branch": "codex/test",
            "dirty_worktree": false,
            "version": "",
        ],
        "environment": [
            "platform": "Darwin",
            "macos_version": "15.5",
            "machine": "arm64",
            "processor": "Apple M4 Max",
        ],
        "target": [
            "model_id": "melix-dev-text",
            "task_kind": "text-generation",
            "source_repo": "HuggingFaceH4/ultrachat_200k",
            "runtime_backend": "mlx",
        ],
        "dataset": [
            "suite_ids": [suiteID],
            "dataset_id": datasetID,
            "sample_size": 2,
            "scoring_mode": evaluation ? "normalized_exact_match" : "",
        ],
        "parameters": parameters,
        "reproducibility": [
            "schema_sha256": "schema-digest",
        ],
        "metrics": [
            [
                "name": metricName,
                "value": evaluation ? 0.75 : 24.5,
                "unit": metricUnit,
            ],
        ],
        "resources": [
            "peak_memory_bytes": 1024,
        ],
        "artifact_root": runRoot.path,
        "artifacts": [
            [
                "kind": evaluation ? "summary_json" : "evidence",
                "path": runRoot.appendingPathComponent(evaluation ? "evaluation-summary.json" : "run-evidence.json").path,
                "relative_path": evaluation ? "evaluation-summary.json" : "run-evidence.json",
            ],
            [
                "kind": "run_record",
                "path": runRoot.appendingPathComponent("run-record.json").path,
                "relative_path": "run-record.json",
            ],
        ],
        "known_gaps": [
            "Apple Silicon telemetry artifact was not present for this run.",
        ],
        "probes": [
            [
                "component": "worker.productization.run_records",
                "phase": "run_record_write",
                "duration_ms": 0.1,
                "status": "completed",
            ],
        ],
    ]
}

private struct NonMelixPipelineTestError: Error, CustomStringConvertible {
    let message: String

    var description: String {
        message
    }
}

private func makeBenchmarkExportBundleJSON() -> String {
    """
    {
      "export_schema_version": "melix.benchmark_export.v1",
      "exported_at_unix_ms": 1712101234567,
      "benchmark_jobs": [
        {
          "schema_version": "melix.serving_benchmark_job.v1",
          "job_id": "bench-1",
          "model_id": "melix-dev-text",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "suites": ["smoke"],
          "parameters": {
            "sample_size": "4",
            "batch_factor": "2"
          },
          "status": "completed",
          "output_dir": "/tmp/melix/bench/runs/bench-1",
          "created_at_unix_ms": 1712100000000,
          "updated_at_unix_ms": 1712100005000,
          "suite_metadata": {
            "smoke": {
              "title": "UltraChat Smoke",
              "dataset_path": "HuggingFaceH4/ultrachat_200k",
              "dataset_name": "default",
              "dataset_split": "train_sft",
              "sample_size": 4,
              "batch_factor": 2
            }
          }
        }
      ],
      "benchmark_results": [
        {
          "schema_version": "melix.serving_benchmark_result.v1",
          "job_id": "bench-1",
          "suite": "smoke",
          "metrics": [
            {"name": "bench.smoke.ttft_ms", "value": 24.45, "unit": "ms"},
            {"name": "bench.smoke.tokens_per_second", "value": 47.08, "unit": "tok/s"}
          ],
          "report_path": "/tmp/melix/bench/runs/bench-1/bench-report.md",
          "report_markdown": "# Melix Bench\\n"
        }
      ],
      "benchmark_matrix_jobs": [
        {
          "schema_version": "melix.benchmark_matrix_job.v1",
          "job_id": "bench-matrix-1",
          "model_id": "melix-dev-text",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "suite_ids": ["smoke"],
          "benchmark_mode": "matrix",
          "status": "completed",
          "output_dir": "/tmp/melix/bench/matrix-runs/bench-matrix-1",
          "created_at_unix_ms": 1712200000000,
          "updated_at_unix_ms": 1712200005000
        }
      ],
      "benchmark_matrix_summary_rows": [
        {
          "job_id": "bench-matrix-1",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "model_id": "melix-dev-text",
          "suite_id": "smoke",
          "context_length": 1024,
          "generation_length": 128,
          "batch_size": 2,
          "cache_profile": "cold",
          "reasoning_mode": "enabled",
          "structured_output_mode": "plain_text",
          "concurrency_level": 1,
          "repeats": 3,
          "requests": 24,
          "duration_seconds": 0,
          "ttft_mean_ms": 24.45,
          "ttft_std_ms": 1.2,
          "request_latency_mean_ms": 88.4,
          "request_latency_std_ms": 3.1,
          "prefill_tokens_per_second_mean": 1400.0,
          "decode_tokens_per_second_mean": 58.2,
          "throughput_requests_per_second": 3.8,
          "throughput_tokens_per_second": 221.5,
          "success_rate": 1.0,
          "peak_memory_bytes_max": 2147483648,
          "queue_wait_mean_ms": 5.1,
          "queue_wait_p95_ms": 9.2,
          "created_at_unix_ms": 1712200000000
        }
      ],
      "benchmark_matrix_request_rows": [
        {
          "job_id": "bench-matrix-1",
          "cell_id": "cell-1",
          "task_kind": "text-generation",
          "suite_id": "smoke",
          "context_length": 1024,
          "generation_length": 128,
          "batch_size": 2,
          "cache_profile": "cold",
          "reasoning_mode": "enabled",
          "structured_output_mode": "plain_text",
          "concurrency_level": 1,
          "repeat_index": 0,
          "request_index": 0,
          "ttft_ms": 24.45,
          "request_latency_ms": 88.4,
          "prefill_tokens_per_second": 1400.0,
          "decode_tokens_per_second": 58.2,
          "queue_wait_ms": 5.1,
          "peak_memory_bytes": 2147483648,
          "status": "completed",
          "error_code": "",
          "created_at_unix_ms": 1712200000000
        }
      ],
      "evaluation_jobs": [
        {
          "schema_version": "melix.evaluation_job.v1",
          "job_id": "eval-1",
          "model_id": "melix-dev-text",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_size": 8,
          "scoring_mode": "multiple_choice_accuracy",
          "parameters": {
            "few_shot": "4"
          },
          "status": "completed",
          "output_dir": "/tmp/melix/evaluation/runs/eval-1",
          "created_at_unix_ms": 1712400000000,
          "updated_at_unix_ms": 1712400005000
        }
      ],
      "evaluation_results": [
        {
          "schema_version": "melix.evaluation_result.v1",
          "job_id": "eval-1",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_size": 8,
          "metrics": [
            {"name": "eval.mmlu.accuracy", "value": 0.75, "unit": "ratio"}
          ],
          "report_path": "/tmp/melix/evaluation/runs/eval-1/evaluation-result.json"
        }
      ],
      "evaluation_summary_rows": [
        {
          "job_id": "eval-1",
          "model_id": "melix-dev-text",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_size": 8,
          "score_name": "eval.mmlu.accuracy",
          "score_value": 0.75,
          "correct_count": 6,
          "incorrect_count": 2,
          "effect_threshold": 0.1,
          "verdict": "improvement",
          "bootstrap_lower_bound": 0.12,
          "bootstrap_upper_bound": 0.41,
          "analytical_lower_bound": 0.1,
          "analytical_upper_bound": 0.38,
          "duration_seconds": 12.5,
          "created_at_unix_ms": 1712400000000
        }
      ],
      "evaluation_samples": [
        {
          "schema_version": "melix.evaluation_sample.v1",
          "job_id": "eval-1",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_id": "sample-1",
          "task_kind": "text-generation",
          "question": "2+2?",
          "expected": "4",
          "predicted": "4",
          "raw_response": "4",
          "correct": true,
          "time_s": 0.01,
          "parse_status": "parsed",
          "input_modalities": ["text"],
          "media_references": [],
          "code_language": "python",
          "code_entry_point": "solve",
          "code_compile_status": "compiled",
          "code_runtime_status": "ok",
          "code_timeout_status": "ok",
          "code_test_status": "passed",
          "code_tests_passed": 2,
          "code_tests_total": 2,
          "code_failure_detail": "",
          "category_label": "math",
          "subject_label": "algebra"
        }
      ],
      "evaluation_compare_jobs": [
        {
          "schema_version": "melix.evaluation_compare_job.v1",
          "job_id": "eval-compare-1",
          "base_model_id": "melix-dev-text",
          "target_model_ids": ["melix-dev-text-lora-a"],
          "task_kind": "text-generation",
          "source_repo": "openai_humaneval",
          "suite_id": "mbpp",
          "dataset_id": "mbpp.dev.v1",
          "sample_size": 2,
          "scoring_mode": "pass_at_1",
          "parameters": {
            "compare_mode": "base_vs_targets",
            "compare_target_model_ids": "melix-dev-text-lora-a"
          },
          "status": "completed",
          "output_dir": "/tmp/melix/evaluation/runs/eval-compare-1",
          "created_at_unix_ms": 1712500000000,
          "updated_at_unix_ms": 1712500005000
        }
      ],
      "evaluation_compare_summary_rows": [
        {
          "schema_version": "melix.evaluation_compare_summary.v1",
          "job_id": "eval-compare-1",
          "base_model_id": "melix-dev-text",
          "target_model_id": "melix-dev-text-lora-a",
          "suite_id": "mbpp",
          "dataset_id": "mbpp.dev.v1",
          "sample_size": 2,
          "scoring_mode": "pass_at_1",
          "win_count": 1,
          "loss_count": 0,
          "tie_count": 1,
          "regression_count": 0,
          "base_accuracy": 0.5,
          "target_accuracy": 1.0,
          "delta_accuracy": 0.5,
          "duration_seconds": 1.75,
          "metrics": [
            {"name": "eval.compare.win_count", "value": 1.0, "unit": "count"},
            {"name": "eval.compare.delta_accuracy", "value": 0.5, "unit": "ratio"}
          ],
          "report_path": "/tmp/melix/evaluation/runs/eval-compare-1/evaluation-compare-report.md"
        }
      ],
      "evaluation_compare_samples": [
        {
          "schema_version": "melix.evaluation_compare_sample.v1",
          "job_id": "eval-compare-1",
          "suite_id": "mbpp",
          "dataset_id": "mbpp.dev.v1",
          "sample_id": "sample-1",
          "target_model_id": "melix-dev-text-lora-a",
          "question": "Write solve(n) that returns n",
          "expected": "solve",
          "base_predicted": "def solve(n):\\n    return 0",
          "target_predicted": "def solve(n):\\n    return n",
          "base_raw_response": "def solve(n):\\n    return 0",
          "target_raw_response": "def solve(n):\\n    return n",
          "base_correct": false,
          "target_correct": true,
          "outcome": "win",
          "regression": false,
          "base_time_s": 0.11,
          "target_time_s": 0.09,
          "base_parse_status": "parsed_code_fallback",
          "target_parse_status": "parsed_code_fallback",
          "code_language": "python",
          "code_entry_point": "solve",
          "base_code_compile_status": "compiled",
          "target_code_compile_status": "compiled",
          "base_code_runtime_status": "ok",
          "target_code_runtime_status": "ok",
          "base_code_timeout_status": "ok",
          "target_code_timeout_status": "ok",
          "base_code_test_status": "failed",
          "target_code_test_status": "passed",
          "base_code_tests_passed": 1,
          "target_code_tests_passed": 2,
          "base_code_tests_total": 2,
          "target_code_tests_total": 2,
          "base_code_failure_detail": "assertion failed",
          "target_code_failure_detail": "",
          "category_label": "math",
          "subject_label": "algebra"
        }
      ]
    }
    """
}

private func makeEvaluationCompareExportBundleJSON() -> String {
    """
    {
      "export_schema_version": "melix.benchmark_export.v1",
      "evaluation_jobs": [
        {
          "schema_version": "melix.evaluation_job.v1",
          "job_id": "eval-compare-2",
          "model_id": "melix-dev-text",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_size": 8,
          "scoring_mode": "multiple_choice_accuracy",
          "parameters": {
            "compare_mode": "base_vs_targets",
            "compare_target_model_ids": "melix-dev-text-lora-a,melix-dev-text-lora-b"
          },
          "status": "completed",
          "output_dir": "/tmp/melix/evaluation/runs/eval-compare-2",
          "created_at_unix_ms": 1712400000000,
          "updated_at_unix_ms": 1712400005000
        }
      ],
      "evaluation_summary_rows": [
        {
          "job_id": "eval-compare-2",
          "model_id": "melix-dev-text-lora-a",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_size": 8,
          "score_name": "eval.compare.delta_accuracy",
          "score_value": 0.25,
          "correct_count": 7,
          "incorrect_count": 1,
          "effect_threshold": 0.1,
          "verdict": "improvement",
          "bootstrap_lower_bound": 0.12,
          "bootstrap_upper_bound": 0.41,
          "analytical_lower_bound": 0.1,
          "analytical_upper_bound": 0.38,
          "duration_seconds": 12.5,
          "created_at_unix_ms": 1712400000000
        },
        {
          "job_id": "eval-compare-2",
          "model_id": "melix-dev-text-lora-b",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_size": 8,
          "score_name": "eval.compare.delta_accuracy",
          "score_value": -0.125,
          "correct_count": 3,
          "incorrect_count": 5,
          "effect_threshold": 0.1,
          "verdict": "inconclusive",
          "bootstrap_lower_bound": -0.21,
          "bootstrap_upper_bound": 0.02,
          "analytical_lower_bound": -0.18,
          "analytical_upper_bound": 0.01,
          "duration_seconds": 12.5,
          "created_at_unix_ms": 1712400000000
        }
      ]
    }
    """
}

private func makeEvaluationCompareSparseExportBundleJSON() -> String {
    """
    {
      "export_schema_version": "melix.benchmark_export.v1",
      "evaluation_jobs": [
        {
          "schema_version": "melix.evaluation_job.v1",
          "job_id": "eval-compare-2",
          "model_id": "melix-dev-text",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_size": 8,
          "scoring_mode": "multiple_choice_accuracy",
          "parameters": {
            "compare_mode": "base_vs_targets",
            "compare_target_model_ids": "melix-dev-text-lora-a"
          },
          "status": "completed",
          "output_dir": "/tmp/melix/evaluation/runs/eval-compare-2",
          "created_at_unix_ms": 1712400000000,
          "updated_at_unix_ms": 1712400005000
        }
      ],
      "evaluation_summary_rows": [
        {
          "job_id": "eval-compare-2",
          "model_id": "",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_size": 8,
          "score_name": "eval.compare.delta_accuracy",
          "score_value": -0.125,
          "correct_count": 3,
          "incorrect_count": 5,
          "verdict": "inconclusive",
          "duration_seconds": 12.5,
          "created_at_unix_ms": 1712400000000
        }
      ]
    }
    """
}

private func makeBenchmarkMatrixJobSummary(
    jobID: String,
    modelID: String,
    taskKind: String,
    sourceRepo: String
) -> Melix_Controlplane_V1_BenchmarkMatrixJobSummary {
    var job = Melix_Controlplane_V1_BenchmarkMatrixJobSummary()
    job.schemaVersion = "melix.benchmark_matrix_job.v1"
    job.jobID = jobID
    job.modelID = modelID
    job.taskKind = taskKind
    job.sourceRepo = sourceRepo
    job.benchmarkMode = "matrix"
    job.status = "completed"
    job.outputDir = "/tmp/melix/bench/matrix-runs/\(jobID)"
    job.createdAtUnixMs = 1712200000000
    job.updatedAtUnixMs = 1712200005000
    return job
}

private func makeBenchmarkMatrixSummaryRow(
    jobID: String,
    taskKind: String,
    sourceRepo: String,
    modelID: String,
    suiteID: String,
    contextLength: UInt32,
    generationLength: UInt32,
    batchSize: UInt32,
    cacheProfile: String,
    reasoningMode: String,
    structuredOutputMode: String,
    concurrencyLevel: UInt32,
    repeats: UInt32,
    requests: UInt32,
    durationSeconds: UInt32,
    ttftMeanMS: Double
) -> Melix_Controlplane_V1_BenchmarkMatrixSummaryRow {
    var row = Melix_Controlplane_V1_BenchmarkMatrixSummaryRow()
    row.jobID = jobID
    row.taskKind = taskKind
    row.sourceRepo = sourceRepo
    row.modelID = modelID
    row.suiteID = suiteID
    row.contextLength = contextLength
    row.generationLength = generationLength
    row.batchSize = batchSize
    row.cacheProfile = cacheProfile
    row.reasoningMode = reasoningMode
    row.structuredOutputMode = structuredOutputMode
    row.concurrencyLevel = concurrencyLevel
    row.repeats = repeats
    row.requests = requests
    row.durationSeconds = durationSeconds
    row.ttftMeanMs = ttftMeanMS
    row.createdAtUnixMs = 1712200000000
    return row
}

private func makeEmptyBenchmarkExportBundleJSON() -> String {
    """
    {
      "export_schema_version": "melix.benchmark_export.v1",
      "benchmark_jobs": [],
      "benchmark_results": [],
      "evaluation_jobs": [],
      "evaluation_results": [],
      "evaluation_samples": []
    }
    """
}

private func makeEvaluationRunResult(
    jobID: String,
    modelID: String = "melix-dev-text",
    suiteID: String,
    datasetID: String,
    metricName: String,
    metricValue: Double
) -> ControlPlaneEvaluationResult {
    var job = Melix_Controlplane_V1_EvaluationJobSummary()
    job.schemaVersion = "melix.evaluation_job.v1"
    job.jobID = jobID
    job.modelID = modelID
    job.taskKind = "text-generation"
    job.sourceRepo = "HuggingFaceH4/ultrachat_200k"
    job.suiteID = suiteID
    job.datasetID = datasetID
    job.sampleSize = 8
    job.scoringMode = "multiple_choice_accuracy"
    job.status = "completed"
    job.outputDir = "/tmp/melix/evaluation/runs/\(jobID)"
    job.createdAtUnixMs = 1712400000000
    job.updatedAtUnixMs = 1712400005000

    var metric = Melix_Controlplane_V1_BenchmarkMetricValue()
    metric.name = metricName
    metric.value = metricValue
    metric.unit = "ratio"

    var result = Melix_Controlplane_V1_EvaluationResultSummary()
    result.schemaVersion = "melix.evaluation_result.v1"
    result.jobID = jobID
    result.suiteID = suiteID
    result.datasetID = datasetID
    result.sampleSize = 8
    result.metrics = [metric]
    result.reportPath = "/tmp/melix/evaluation/runs/\(jobID)/evaluation-result.json"
    return ControlPlaneEvaluationResult(job: job, results: [result])
}

private func makeEvaluationCompareResult(
    jobID: String,
    baseSuiteID: String,
    datasetID: String,
    targets: [(modelID: String, metricValue: Double)],
    status: String = "completed"
) -> ControlPlaneEvaluationResult {
    var job = Melix_Controlplane_V1_EvaluationJobSummary()
    job.schemaVersion = "melix.evaluation_job.v1"
    job.jobID = jobID
    job.modelID = "melix-dev-text"
    job.taskKind = "text-generation"
    job.sourceRepo = "HuggingFaceH4/ultrachat_200k"
    job.suiteID = baseSuiteID
    job.datasetID = datasetID
    job.sampleSize = 8
    job.scoringMode = "multiple_choice_accuracy"
    job.status = status
    job.outputDir = "/tmp/melix/evaluation/runs/\(jobID)"
    job.createdAtUnixMs = 1712400000000
    job.updatedAtUnixMs = 1712400005000

    let results = targets.map { target in
        var metric = Melix_Controlplane_V1_BenchmarkMetricValue()
        metric.name = "eval.compare.win_rate"
        metric.value = target.metricValue
        metric.unit = "ratio"

        var result = Melix_Controlplane_V1_EvaluationResultSummary()
        result.schemaVersion = "melix.evaluation_result.v1"
        result.jobID = jobID
        result.suiteID = "\(baseSuiteID):\(target.modelID)"
        result.datasetID = datasetID
        result.sampleSize = 8
        result.metrics = [metric]
        result.reportPath = "/tmp/melix/evaluation/runs/\(jobID)/\(target.modelID)-result.json"
        return result
    }

    return ControlPlaneEvaluationResult(job: job, results: results)
}

private func writeFakeBatchCLI(_ path: URL, failEval: Bool = false, warnBench: Bool = false) throws {
    let failEvalLiteral = failEval ? "1" : "0"
    let warnBenchLiteral = warnBench ? "1" : "0"
    let script = """
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p "${MELIX_BATCH_MODEL_DIR}/fake-raw"
    printf '{"raw": true}\\n' > "${MELIX_BATCH_MODEL_DIR}/fake-raw/raw.json"
    if [[ "$1 $2" == "bench run" ]]; then
      if [[ "\(warnBenchLiteral)" == "1" ]]; then
        printf 'bench warning for %s\\n' "${MELIX_BATCH_MODEL_INDEX}" >&2
      fi
      printf '{"job_id":"bench-01","metrics":{"bench.smoke.tokens_per_second":12.5},"output_dir":"%s"}\\n' "${MELIX_BATCH_MODEL_DIR}/fake-raw"
      exit 0
    fi
    if [[ "$1 $2" == "bench export-csv" ]]; then
      output=""
      while [[ $# -gt 0 ]]; do
        case "$1" in
          --output) output="$2"; shift 2 ;;
          *) shift ;;
        esac
      done
      mkdir -p "$(dirname "$output")"
      printf 'job_id,metric,value\\nbench-01,bench.smoke.tokens_per_second,12.5\\n' > "$output"
      printf '{"output":"%s"}\\n' "$output"
      exit 0
    fi
    if [[ "$1 $2" == "eval run" ]]; then
      if [[ "\(failEvalLiteral)" == "1" ]]; then
        printf 'Semantic judge remote server returned 401 unauthorized\\n' >&2
        exit 2
      fi
      printf '{"job_id":"eval-01","metrics":{"eval.event_extraction.semantic_f1":0.9},"output_dir":"%s"}\\n' "${MELIX_BATCH_MODEL_DIR}/fake-raw"
      exit 0
    fi
    if [[ "$1 $2" == "eval export-summary-csv" || "$1 $2" == "eval export-samples-csv" || "$1 $2" == "eval export-samples-jsonl" ]]; then
      output=""
      while [[ $# -gt 0 ]]; do
        case "$1" in
          --output) output="$2"; shift 2 ;;
          *) shift ;;
        esac
      done
      mkdir -p "$(dirname "$output")"
      printf 'job_id,metric,value\\neval-01,eval.event_extraction.semantic_f1,0.9\\n' > "$output"
      printf '{"output":"%s"}\\n' "$output"
      exit 0
    fi
    printf 'unexpected fake melix command: %s\\n' "$*" >&2
    exit 64
    """
    try script.write(to: path, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: path.path)
}
