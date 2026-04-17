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
        result.models = [model]
        await client.setHubSearchResult(result)

        let output = try await MelixCLIRunner(client: client).run(
            .modelHubSearch(.init(query: "qwen3.5", pageSize: 5, cursor: "", mlxOnly: true, json: false))
        )

        #expect(output.contains("repo_id\tpipeline_tag\tcompatibility"))
        #expect(output.contains("mlx-community/Qwen3.5-0.8B-OptiQ-4bit\ttext-generation\tmlx"))
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
        await client.setHubModelCard(card)

        let output = try await MelixCLIRunner(client: client).run(
            .modelHubShow(.init(repoID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit", json: false))
        )

        #expect(output.contains("repo_id=mlx-community/Qwen3.5-0.8B-OptiQ-4bit"))
        #expect(output.contains("author=mlx-community"))
        #expect(output.contains("mlx_compatible=true"))
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
        let jsonOutput = try await MelixCLIRunner(client: client).run(.doctor(.init(json: true)))
        let payload = try #require(parseJSONObject(jsonOutput))
        let findings = try #require(payload["findings"] as? [[String: Any]])

        #expect(textOutput.contains("# Melix Doctor"))
        #expect(payload["markdown"] as? String == "# Melix Doctor\n\n- worker_state: idle\n")
        #expect(payload["health_status"] as? String == "healthy")
        #expect(findings.count == 1)
        #expect(findings[0]["code"] as? String == "cache_warning")
        #expect(findings[0]["severity"] as? String == "warning")
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
                outputPath: "/tmp/melix-managed/huggingface/mlx-community/Qwen3.5-0.8B-OptiQ-4bit/main",
                manifestJSON: #"""
                {
                  "model_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                  "ext": {
                    "melix.source_kind": "hub_repo",
                    "melix.source_locator": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
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
                "/tmp/melix-managed/huggingface/mlx-community/Qwen3.5-0.8B-OptiQ-4bit/main"
        )
        #expect(payload["source_kind"] as? String == "hub_repo")
        #expect(payload["source_locator"] as? String == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
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
                    modelID: "melix-dev-vlm",
                    host: "127.0.0.1",
                    port: 12434
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
        #expect(sessions.first?["model_id"] as? String == "melix-dev-vlm")

        _ = try await runner.run(
            .serverStart(.init(serverSessionID: "server-session-1"))
        )

        let gatewayConfigCall = try #require(await client.lastGatewayConfigApplyRequest)
        let servingDefaultsCall = try #require(await client.lastServingDefaultsApplyRequest)

        #expect(gatewayConfigCall.serverSessionID == "server-session-1")
        #expect(gatewayConfigCall.servedModelID == "melix-dev-vlm")
        #expect(servingDefaultsCall.serverSessionID == "server-session-1")

        try await store.save(
            MelixOperatorSessionState(
                selectedSurfaceID: "server",
                selectedToolSectionID: "modelsLibrary",
                selectedServerSessionID: "server-session-1",
                serverSessions: [
                    .init(
                        id: "server-session-1",
                        title: "Broken Session",
                        modelID: "melix-dev-ocr"
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
                        modelID: importedModelID
                    )
                ]
            )
        )

        _ = try await MelixCLIRunner(client: client, operatorSessionStore: store).run(
            .serverStart(.init(serverSessionID: "server-session-1"))
        )

        let gatewayConfigCall = try #require(await client.lastGatewayConfigApplyRequest)
        let startedAction = try #require(await client.lastServerAction)

        #expect(gatewayConfigCall.servedModelID == importedModelID)
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
        #expect(output == #"{"adapters":[{"adapter_name":"demo-adapter"}]}"#)
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

        #expect(output == "No adapters found.\n")
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
        #expect(command.contains("--seed"))
        #expect(command.contains("--scoring-mode"))
        #expect(command.contains("--code-exec-policy"))
        #expect(command.last == "--json")
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
        let components = output.split(separator: ":", maxSplits: 2).map(String.init)

        #expect(components.count == 3)
        #expect(components[0] == "configured")
        #expect(
            URL(fileURLWithPath: components[1]).resolvingSymlinksInPath().path ==
            root.resolvingSymlinksInPath().path
        )
        #expect(components[2] == "runner-arg")
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
            kvQuant: "q8"
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
