import Foundation
import Testing

@testable import MelixControlPlaneCore

@Suite("OpenAI Conformance Harness")
struct OpenAIConformanceHarnessTests {
    @Test("mock backend CI mode emits existing conformance report schema")
    func mockBackendCIModeEmitsExistingConformanceReportSchema() async throws {
        let harness = OpenAIConformanceHarness(
            target: .mockBackendCI(modelID: "melix-dev-text")
        )

        let report = try await harness.run()

        #expect(report.schemaVersion == OpenAIConformanceReport.currentSchemaVersion)
        #expect(report.summary.total == 3)
        #expect(report.summary.passed == 3)
        #expect(report.summary.failed == 0)
        #expect(report.rows.map(\.field) == [
            "chat.completions.response_shape",
            "chat.completions.streaming_tool_call_shape",
            "chat.completions.error_shape",
        ])
    }

    @Test("real backend smoke mode normalizes base URL and carries model and auth")
    func realBackendSmokeModeNormalizesBaseURLAndCarriesModelAndAuth() async throws {
        let transport = RecordingConformanceTransport(responses: [
            .json(statusCode: 200, body: chatCompletionBody()),
            .sse(statusCode: 200, body: streamingToolCallBody()),
            .json(statusCode: 400, body: errorBody(field: "best_of", phase: "openai_request_validation")),
        ])
        let harness = OpenAIConformanceHarness(
            target: .realBackendSmoke(
                baseURL: " https://provider.example/v1/ ",
                modelID: "remote-model",
                apiKey: "sk-secret",
                timeoutSeconds: 12
            ),
            transport: transport
        )

        let report = try await harness.run()
        let requests = await transport.requests

        #expect(report.summary.passed == 3)
        #expect(requests.count == 3)
        #expect(requests.allSatisfy { $0.url?.absoluteString == "https://provider.example/v1/chat/completions" })
        #expect(requests.allSatisfy { $0.value(forHTTPHeaderField: "Authorization") == "Bearer sk-secret" })
        #expect(requests.allSatisfy { $0.timeoutInterval == 12 })
        #expect(try requests.allSatisfy { try requestBodyModel($0) == "remote-model" })
    }

    @Test("real backend smoke mode accepts a base URL that already targets chat completions")
    func realBackendSmokeModeAcceptsChatCompletionsBaseURL() async throws {
        let transport = RecordingConformanceTransport(responses: [
            .json(statusCode: 200, body: chatCompletionBody()),
            .sse(statusCode: 200, body: streamingToolCallBody()),
            .json(statusCode: 400, body: errorBody(field: "best_of", phase: "openai_request_validation")),
        ])
        let harness = OpenAIConformanceHarness(
            target: .realBackendSmoke(
                baseURL: " https://provider.example/openai/v1/chat/completions/ ",
                modelID: "remote-model",
                apiKey: "",
                timeoutSeconds: 30
            ),
            transport: transport
        )

        let report = try await harness.run()
        let requests = await transport.requests

        #expect(report.summary.passed == 3)
        #expect(requests.count == 3)
        #expect(requests.allSatisfy {
            $0.url?.absoluteString == "https://provider.example/openai/v1/chat/completions"
        })
    }

    @Test("error row observed reason names status field and phase")
    func errorRowObservedReasonNamesStatusFieldAndPhase() async throws {
        let transport = RecordingConformanceTransport(responses: [
            .json(statusCode: 200, body: chatCompletionBody()),
            .sse(statusCode: 200, body: streamingToolCallBody()),
            .json(statusCode: 400, body: errorBody(field: "best_of", phase: "openai_request_validation")),
        ])
        let harness = OpenAIConformanceHarness(
            target: .realBackendSmoke(
                baseURL: "https://provider.example/v1",
                modelID: "remote-model",
                apiKey: "",
                timeoutSeconds: 0
            ),
            transport: transport
        )

        let report = try await harness.run()
        let errorRow = try #require(report.rows.first { $0.field == "chat.completions.error_shape" })

        #expect(errorRow.observedStatus == .pass)
        #expect(errorRow.observedReason == "status=400 field=best_of phase=openai_request_validation")
        #expect(await transport.requests.last?.value(forHTTPHeaderField: "Authorization") == nil)
    }

    @Test("CLI parser returns named usage errors for missing real backend fields")
    func cliParserReturnsNamedUsageErrorsForMissingRealBackendFields() throws {
        #expect(throws: OpenAIConformanceHarnessCLIError.missingValue("--output")) {
            try OpenAIConformanceHarnessCLI.parse(arguments: ["--mode", "mock-backend-ci"])
        }
        #expect(throws: OpenAIConformanceHarnessCLIError.missingValue("--base-url")) {
            try OpenAIConformanceHarnessCLI.parse(
                arguments: ["--mode", "real-backend-smoke", "--model", "remote-model", "--output", "report.json"]
            )
        }
        #expect(throws: OpenAIConformanceHarnessCLIError.missingValue("--model")) {
            try OpenAIConformanceHarnessCLI.parse(
                arguments: ["--mode", "real-backend-smoke", "--base-url", "https://provider.example/v1", "--output", "report.json"]
            )
        }
    }

    @Test("CLI parser covers valid modes invalid options and artifact writing")
    func cliParserCoversValidModesInvalidOptionsAndArtifactWriting() async throws {
        let mockOutput = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-openai-conformance-\(UUID().uuidString)")
            .appendingPathComponent("mock-report.json")
        let mockCLI = try OpenAIConformanceHarnessCLI.parse(arguments: [
            "--mode", "mock-backend-ci",
            "--model", "mock-model",
            "--output", mockOutput.path,
        ])

        #expect(mockCLI.target == .mockBackendCI(modelID: "mock-model"))
        let mockReport = try await mockCLI.run()
        #expect(mockReport.summary.passed == 3)
        #expect(FileManager.default.fileExists(atPath: mockOutput.path))

        let realCLI = try OpenAIConformanceHarnessCLI.parse(arguments: [
            "--mode", "real-backend-smoke",
            "--base-url", "https://provider.example/v1",
            "--model", "remote-model",
            "--api-key", "sk-secret",
            "--timeout-seconds", "9",
            "--output", "real-report.json",
        ])
        #expect(realCLI.target == .realBackendSmoke(
            baseURL: "https://provider.example/v1",
            modelID: "remote-model",
            apiKey: "sk-secret",
            timeoutSeconds: 9
        ))

        let defaultTimeoutCLI = try OpenAIConformanceHarnessCLI.parse(arguments: [
            "--mode", "real-backend-smoke",
            "--base-url", "https://provider.example/v1",
            "--model", "remote-model",
            "--output", "real-report.json",
        ])
        #expect(defaultTimeoutCLI.target == .realBackendSmoke(
            baseURL: "https://provider.example/v1",
            modelID: "remote-model",
            apiKey: "",
            timeoutSeconds: 30
        ))

        let unknown = OpenAIConformanceHarnessCLIError.unknownOption("model")
        let invalidMode = OpenAIConformanceHarnessCLIError.invalidMode("other")
        let invalidTimeout = OpenAIConformanceHarnessCLIError.invalidTimeout("zero")
        #expect(unknown.description == "unknown option: model")
        #expect(invalidMode.description == "invalid --mode: other")
        #expect(invalidTimeout.description == "invalid --timeout-seconds: zero")
        #expect(throws: unknown) {
            try OpenAIConformanceHarnessCLI.parse(arguments: ["model", "x", "--output", "report.json"])
        }
        #expect(throws: OpenAIConformanceHarnessCLIError.unknownOption("--model-id")) {
            try OpenAIConformanceHarnessCLI.parse(arguments: [
                "--mode", "mock-backend-ci",
                "--model-id", "mock-model",
                "--output", "report.json",
            ])
        }
        #expect(throws: OpenAIConformanceHarnessCLIError.missingValue("--mode")) {
            try OpenAIConformanceHarnessCLI.parse(arguments: ["--mode"])
        }
        #expect(throws: invalidMode) {
            try OpenAIConformanceHarnessCLI.parse(arguments: ["--mode", "other", "--output", "report.json"])
        }
        #expect(throws: invalidTimeout) {
            try OpenAIConformanceHarnessCLI.parse(arguments: [
                "--mode", "real-backend-smoke",
                "--base-url", "https://provider.example/v1",
                "--model", "remote-model",
                "--timeout-seconds", "zero",
                "--output", "report.json",
            ])
        }
    }

    @Test("harness records transport failures and rethrows cancellation")
    func harnessRecordsTransportFailuresAndRethrowsCancellation() async throws {
        let failingHarness = OpenAIConformanceHarness(
            target: .realBackendSmoke(
                baseURL: "https://provider.example/v1",
                modelID: "remote-model",
                apiKey: "",
                timeoutSeconds: 30
            ),
            transport: ThrowingConformanceTransport(error: TestTransportError.networkLost)
        )

        let report = try await failingHarness.run()

        #expect(report.summary.failed == 3)
        #expect(report.rows.allSatisfy { $0.observedReason == "transport_failed=networkLost" })
        #expect(OpenAIConformanceHarnessError.transportFailed("bad").description == "OpenAI conformance transport failed: bad")

        let cancellingHarness = OpenAIConformanceHarness(
            target: .realBackendSmoke(
                baseURL: "https://provider.example/v1",
                modelID: "remote-model",
                apiKey: "",
                timeoutSeconds: 30
            ),
            transport: ThrowingConformanceTransport(error: CancellationError())
        )
        do {
            _ = try await cancellingHarness.run()
            Issue.record("expected cancellation to be rethrown")
        } catch is CancellationError {
        }

        let urlSessionCancellingHarness = OpenAIConformanceHarness(
            target: .realBackendSmoke(
                baseURL: "https://provider.example/v1",
                modelID: "remote-model",
                apiKey: "",
                timeoutSeconds: 30
            ),
            transport: ThrowingConformanceTransport(error: URLError(.cancelled))
        )
        await #expect(throws: URLError(.cancelled)) {
            _ = try await urlSessionCancellingHarness.run()
        }
    }

    @Test("harness names invalid base URL and mock malformed requests")
    func harnessNamesInvalidBaseURLAndMockMalformedRequests() async throws {
        let invalidBaseHarness = OpenAIConformanceHarness(
            target: .realBackendSmoke(
                baseURL: " ",
                modelID: "remote-model",
                apiKey: "",
                timeoutSeconds: 30
            )
        )

        await #expect(throws: OpenAIConformanceHarnessError.invalidBaseURL(" ")) {
            _ = try await invalidBaseHarness.run()
        }
        #expect(OpenAIConformanceHarnessError.invalidBaseURL(" ").description == "invalid OpenAI conformance base_url:  ")

        var request = URLRequest(url: URL(string: "https://mock.melix.local/v1/chat/completions")!)
        request.httpMethod = "POST"
        await #expect(throws: OpenAIConformanceHarnessError.transportFailed("mock request body was not JSON")) {
            _ = try await MockOpenAIConformanceTransport().data(for: request)
        }
    }

    @Test("harness records shape failures with row-specific reasons")
    func harnessRecordsShapeFailuresWithRowSpecificReasons() async throws {
        let badNonStreamingStatus = try await runHarness(responses: [
            .json(statusCode: 503, body: "{}"),
            .sse(statusCode: 200, body: streamingToolCallBody()),
            .json(statusCode: 400, body: errorBody(field: "best_of", phase: "openai_request_validation")),
        ])
        #expect(row("chat.completions.response_shape", in: badNonStreamingStatus)?.observedReason == "status=503")

        let malformedNonStreaming = try await runHarness(responses: [
            .json(statusCode: 200, body: "not-json"),
            .sse(statusCode: 200, body: streamingToolCallBody()),
            .json(statusCode: 400, body: errorBody(field: "best_of", phase: "openai_request_validation")),
        ])
        #expect(row("chat.completions.response_shape", in: malformedNonStreaming)?.observedReason == "status=200 missing=choices[0].message")

        let badStreamingStatus = try await runHarness(responses: [
            .json(statusCode: 200, body: chatCompletionBody()),
            .sse(statusCode: 502, body: ""),
            .json(statusCode: 400, body: errorBody(field: "best_of", phase: "openai_request_validation")),
        ])
        #expect(row("chat.completions.streaming_tool_call_shape", in: badStreamingStatus)?.observedReason == "status=502")

        let missingDone = try await runHarness(responses: [
            .json(statusCode: 200, body: chatCompletionBody()),
            .sse(statusCode: 200, body: #"data: {"choices":[{"delta":{"tool_calls":[]},"finish_reason":"tool_calls"}]}"#),
            .json(statusCode: 400, body: errorBody(field: "best_of", phase: "openai_request_validation")),
        ])
        #expect(row("chat.completions.streaming_tool_call_shape", in: missingDone)?.observedReason == "status=200 missing=done")

        let missingToolCall = try await runHarness(responses: [
            .json(statusCode: 200, body: chatCompletionBody()),
            .sse(statusCode: 200, body: "data: [DONE]\n"),
            .json(statusCode: 400, body: errorBody(field: "best_of", phase: "openai_request_validation")),
        ])
        #expect(row("chat.completions.streaming_tool_call_shape", in: missingToolCall)?.observedReason == "status=200 missing=tool_call_chunk")

        let spacedSSE = try await runHarness(responses: [
            .json(statusCode: 200, body: chatCompletionBody()),
            .sse(statusCode: 200, body: streamingToolCallBodyWithJSONWhitespace()),
            .json(statusCode: 400, body: errorBody(field: "best_of", phase: "openai_request_validation")),
        ])
        #expect(row("chat.completions.streaming_tool_call_shape", in: spacedSSE)?.observedStatus == .pass)

        let errorReturnedSuccess = try await runHarness(responses: [
            .json(statusCode: 200, body: chatCompletionBody()),
            .sse(statusCode: 200, body: streamingToolCallBody()),
            .json(statusCode: 200, body: chatCompletionBody()),
        ])
        #expect(row("chat.completions.error_shape", in: errorReturnedSuccess)?.observedReason == "status=200 expected_error=true")

        let errorMissingField = try await runHarness(responses: [
            .json(statusCode: 200, body: chatCompletionBody()),
            .sse(statusCode: 200, body: streamingToolCallBody()),
            .json(statusCode: 400, body: #"{"error":{"phase":"openai_request_validation"}}"#),
        ])
        #expect(row("chat.completions.error_shape", in: errorMissingField)?.observedReason == "status=400 missing=field_or_phase")
    }

    @Test("real backend CLI without injected transport does not fall back to mock")
    func realBackendCLIWithoutInjectedTransportDoesNotFallBackToMock() async throws {
        let output = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-openai-conformance-\(UUID().uuidString)")
            .appendingPathComponent("real-report.json")
        let cli = OpenAIConformanceHarnessCLI(
            target: .realBackendSmoke(
                baseURL: "http://127.0.0.1:9/v1",
                modelID: "remote-model",
                apiKey: "",
                timeoutSeconds: 1
            ),
            outputURL: output
        )

        let report = try await cli.run()

        #expect(report.summary.failed > 0)
        #expect(report.summary.passed == 0)
    }

    @Test("proxy parity harness emits existing report schema for local and remote targets")
    func proxyParityHarnessEmitsExistingReportSchemaForLocalAndRemoteTargets() async throws {
        let localTransport = RecordingConformanceTransport(responses: [
            .json(statusCode: 200, body: chatCompletionBody()),
            .sse(statusCode: 200, body: streamingToolCallBody()),
            .json(statusCode: 400, body: errorBody(field: "best_of", phase: "openai_request_validation")),
        ])
        let remoteTransport = RecordingConformanceTransport(responses: [
            .json(statusCode: 200, body: chatCompletionBody()),
            .sse(statusCode: 200, body: streamingToolCallBody()),
            .json(statusCode: 400, body: errorBody(field: "best_of", phase: "openai_request_validation")),
        ])
        let harness = OpenAIProxyParityHarness(
            target: OpenAIProxyParityTarget(
                localBaseURL: "https://local.example/v1",
                localModelID: "local-model",
                localAPIKey: "local-secret",
                remoteBaseURL: "https://remote.example/openai/v1/",
                remoteModelID: "remote-model",
                remoteAPIKey: "remote-secret",
                timeoutSeconds: 9
            ),
            localTransport: localTransport,
            remoteTransport: remoteTransport
        )

        let report = try await harness.run()
        let localRequests = await localTransport.requests
        let remoteRequests = await remoteTransport.requests

        #expect(report.schemaVersion == OpenAIConformanceReport.currentSchemaVersion)
        #expect(report.summary.total == 3)
        #expect(report.summary.passed == 3)
        #expect(report.summary.failed == 0)
        #expect(report.rows.map(\.field) == [
            "proxy_parity.chat.completions.response_shape",
            "proxy_parity.chat.completions.streaming_tool_call_shape",
            "proxy_parity.chat.completions.error_shape",
        ])
        #expect(report.rows.allSatisfy {
            $0.observedReason == "request_receipt=equivalent response_shape=equivalent"
        })
        #expect(localRequests.count == 3)
        #expect(remoteRequests.count == 3)
        #expect(localRequests.allSatisfy { $0.timeoutInterval == 9 })
        #expect(remoteRequests.allSatisfy { $0.timeoutInterval == 9 })
        #expect(localRequests.allSatisfy { $0.value(forHTTPHeaderField: "Authorization") == "Bearer local-secret" })
        #expect(remoteRequests.allSatisfy { $0.value(forHTTPHeaderField: "Authorization") == "Bearer remote-secret" })
        #expect(remoteRequests.allSatisfy { $0.url?.path == "/openai/v1/chat/completions" })
        #expect(try localRequests.allSatisfy { try requestBodyModel($0) == "local-model" })
        #expect(try remoteRequests.allSatisfy { try requestBodyModel($0) == "remote-model" })
    }

    @Test("proxy parity request receipt mismatches are named without leaking model IDs")
    func proxyParityRequestReceiptMismatchesAreNamedWithoutLeakingModelIDs() async throws {
        let localTransport = RecordingConformanceTransport(responses: [
            .json(statusCode: 200, body: chatCompletionBody()),
            .sse(statusCode: 200, body: streamingToolCallBody()),
            .json(statusCode: 400, body: errorBody(field: "best_of", phase: "openai_request_validation")),
        ])
        let remoteTransport = RecordingConformanceTransport(responses: [
            .json(statusCode: 200, body: chatCompletionBody()),
            .sse(statusCode: 200, body: streamingToolCallBody()),
            .json(statusCode: 400, body: errorBody(field: "best_of", phase: "openai_request_validation")),
        ])
        let harness = OpenAIProxyParityHarness(
            target: OpenAIProxyParityTarget(
                localBaseURL: "https://local.example/v1",
                localModelID: "local-model",
                localAPIKey: "",
                remoteBaseURL: "https://remote.example/v1",
                remoteModelID: "",
                remoteAPIKey: "",
                timeoutSeconds: 30
            ),
            localTransport: localTransport,
            remoteTransport: remoteTransport
        )

        let report = try await harness.run()
        let firstRow = try #require(report.rows.first)

        #expect(report.summary.failed == 3)
        #expect(firstRow.observedReason == "request_receipt.model_present local=true remote=false")
        #expect(firstRow.observedReason.contains("local-model") == false)
    }

    @Test("proxy parity response shape mismatches are named by side")
    func proxyParityResponseShapeMismatchesAreNamedBySide() async throws {
        let localTransport = RecordingConformanceTransport(responses: [
            .json(statusCode: 200, body: chatCompletionBody()),
            .sse(statusCode: 200, body: streamingToolCallBody()),
            .json(statusCode: 400, body: errorBody(field: "best_of", phase: "openai_request_validation")),
        ])
        let remoteTransport = RecordingConformanceTransport(responses: [
            .json(statusCode: 200, body: chatCompletionBody()),
            .sse(statusCode: 200, body: "data: [DONE]\n"),
            .json(statusCode: 400, body: errorBody(field: "best_of", phase: "openai_request_validation")),
        ])
        let harness = OpenAIProxyParityHarness(
            target: OpenAIProxyParityTarget(
                localBaseURL: "https://local.example/v1",
                localModelID: "melix-dev-text",
                localAPIKey: "",
                remoteBaseURL: "https://remote.example/v1",
                remoteModelID: "remote-model",
                remoteAPIKey: "",
                timeoutSeconds: 30
            ),
            localTransport: localTransport,
            remoteTransport: remoteTransport
        )

        let report = try await harness.run()
        let streamingRow = try #require(
            report.rows.first { $0.field == "proxy_parity.chat.completions.streaming_tool_call_shape" }
        )

        #expect(report.summary.failed == 1)
        #expect(streamingRow.observedReason == "remote_response=status=200 missing=tool_call_chunk")
    }

    @Test("proxy parity names local response and response-shape reason divergences")
    func proxyParityNamesLocalResponseAndResponseShapeReasonDivergences() async throws {
        let localFailure = try await OpenAIProxyParityHarness(
            target: proxyParityTestTarget(),
            localTransport: RecordingConformanceTransport(responses: [
                .json(statusCode: 503, body: "{}"),
                .sse(statusCode: 200, body: streamingToolCallBody()),
                .json(statusCode: 400, body: errorBody(field: "best_of", phase: "openai_request_validation")),
            ]),
            remoteTransport: RecordingConformanceTransport(responses: [
                .json(statusCode: 200, body: chatCompletionBody()),
                .sse(statusCode: 200, body: streamingToolCallBody()),
                .json(statusCode: 400, body: errorBody(field: "best_of", phase: "openai_request_validation")),
            ])
        ).run()
        #expect(
            row("proxy_parity.chat.completions.response_shape", in: localFailure)?.observedReason == "local_response=status=503"
        )

        let reasonDivergence = try await OpenAIProxyParityHarness(
            target: proxyParityTestTarget(),
            localTransport: RecordingConformanceTransport(responses: [
                .json(statusCode: 200, body: chatCompletionBody()),
                .sse(statusCode: 200, body: streamingToolCallBody()),
                .json(statusCode: 400, body: errorBody(field: "best_of", phase: "openai_request_validation")),
            ]),
            remoteTransport: RecordingConformanceTransport(responses: [
                .json(statusCode: 200, body: chatCompletionBody()),
                .sse(statusCode: 200, body: streamingToolCallBody()),
                .json(statusCode: 422, body: errorBody(field: "best_of", phase: "openai_request_validation")),
            ])
        ).run()
        #expect(
            row("proxy_parity.chat.completions.error_shape", in: reasonDivergence)?.observedReason ==
                "response_shape local=status=400 field=best_of phase=openai_request_validation remote=status=422 field=best_of phase=openai_request_validation"
        )
    }

    @Test("proxy parity records transport failures and rethrows cancellation")
    func proxyParityRecordsTransportFailuresAndRethrowsCancellation() async throws {
        let transportFailure = try await OpenAIProxyParityHarness(
            target: proxyParityTestTarget(),
            localTransport: ThrowingConformanceTransport(error: TestTransportError.networkLost),
            remoteTransport: RecordingConformanceTransport(responses: [
                .json(statusCode: 200, body: chatCompletionBody()),
                .sse(statusCode: 200, body: streamingToolCallBody()),
                .json(statusCode: 400, body: errorBody(field: "best_of", phase: "openai_request_validation")),
            ])
        ).run()
        #expect(
            row("proxy_parity.chat.completions.response_shape", in: transportFailure)?.observedReason ==
                "local_response=transport_failed=networkLost"
        )

        let cancellingHarness = OpenAIProxyParityHarness(
            target: proxyParityTestTarget(),
            localTransport: ThrowingConformanceTransport(error: URLError(.cancelled)),
            remoteTransport: RecordingConformanceTransport(responses: [
                .json(statusCode: 200, body: chatCompletionBody()),
            ])
        )
        await #expect(throws: URLError(.cancelled)) {
            _ = try await cancellingHarness.run()
        }

        let cancellationErrorHarness = OpenAIProxyParityHarness(
            target: proxyParityTestTarget(),
            localTransport: ThrowingConformanceTransport(error: CancellationError()),
            remoteTransport: RecordingConformanceTransport(responses: [
                .json(statusCode: 200, body: chatCompletionBody()),
            ])
        )
        do {
            _ = try await cancellationErrorHarness.run()
            Issue.record("expected cancellation to be rethrown")
        } catch is CancellationError {
        }
    }

    @Test("CLI parser covers proxy parity mode and named missing fields")
    func cliParserCoversProxyParityModeAndNamedMissingFields() throws {
        let cli = try OpenAIConformanceHarnessCLI.parse(arguments: [
            "--mode", "proxy-parity",
            "--local-base-url", "https://local.example/v1",
            "--local-model", "local-model",
            "--remote-base-url", "https://remote.example/v1",
            "--remote-model", "remote-model",
            "--remote-api-key", "remote-secret",
            "--timeout-seconds", "11",
            "--output", "parity-report.json",
        ])

        #expect(cli.proxyParityTarget == OpenAIProxyParityTarget(
            localBaseURL: "https://local.example/v1",
            localModelID: "local-model",
            localAPIKey: "",
            remoteBaseURL: "https://remote.example/v1",
            remoteModelID: "remote-model",
            remoteAPIKey: "remote-secret",
            timeoutSeconds: 11
        ))
        #expect(throws: OpenAIConformanceHarnessCLIError.missingValue("--local-base-url")) {
            try OpenAIConformanceHarnessCLI.parse(arguments: [
                "--mode", "proxy-parity",
                "--local-model", "local-model",
                "--remote-base-url", "https://remote.example/v1",
                "--remote-model", "remote-model",
                "--output", "parity-report.json",
            ])
        }
        #expect(throws: OpenAIConformanceHarnessCLIError.missingValue("--remote-model")) {
            try OpenAIConformanceHarnessCLI.parse(arguments: [
                "--mode", "proxy-parity",
                "--local-base-url", "https://local.example/v1",
                "--local-model", "local-model",
                "--remote-base-url", "https://remote.example/v1",
                "--output", "parity-report.json",
            ])
        }
        #expect(throws: OpenAIConformanceHarnessCLIError.missingValue("--local-model")) {
            try OpenAIConformanceHarnessCLI.parse(arguments: [
                "--mode", "proxy-parity",
                "--local-base-url", "https://local.example/v1",
                "--remote-base-url", "https://remote.example/v1",
                "--remote-model", "remote-model",
                "--output", "parity-report.json",
            ])
        }
        #expect(throws: OpenAIConformanceHarnessCLIError.missingValue("--remote-base-url")) {
            try OpenAIConformanceHarnessCLI.parse(arguments: [
                "--mode", "proxy-parity",
                "--local-base-url", "https://local.example/v1",
                "--local-model", "local-model",
                "--remote-model", "remote-model",
                "--output", "parity-report.json",
            ])
        }
        #expect(throws: OpenAIConformanceHarnessCLIError.unknownOption("--remote-base-url")) {
            try OpenAIConformanceHarnessCLI.parse(arguments: [
                "--mode", "mock-backend-ci",
                "--remote-base-url", "https://remote.example/v1",
                "--output", "report.json",
            ])
        }
        #expect(throws: OpenAIConformanceHarnessCLIError.unknownOption("--base-url")) {
            try OpenAIConformanceHarnessCLI.parse(arguments: [
                "--mode", "proxy-parity",
                "--base-url", "https://local.example/v1",
                "--model", "local-model",
                "--local-base-url", "https://local.example/v1",
                "--local-model", "local-model",
                "--remote-base-url", "https://remote.example/v1",
                "--remote-model", "remote-model",
                "--output", "parity-report.json",
            ])
        }
    }

    @Test("proxy parity CLI run writes report using injected transport")
    func proxyParityCLIRunWritesReportUsingInjectedTransport() async throws {
        let output = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-openai-proxy-parity-\(UUID().uuidString)")
            .appendingPathComponent("parity-report.json")
        let cli = OpenAIConformanceHarnessCLI(
            proxyParityTarget: proxyParityTestTarget(),
            outputURL: output
        )

        let report = try await cli.run(transport: MockOpenAIConformanceTransport())
        let decoded = try JSONDecoder().decode(
            OpenAIConformanceReport.self,
            from: try Data(contentsOf: output)
        )

        #expect(report.summary.passed == 3)
        #expect(decoded == report)
    }
}

private actor RecordingConformanceTransport: RemoteProviderHTTPTransport {
    enum Response {
        case json(statusCode: Int, body: String)
        case sse(statusCode: Int, body: String)
    }

    private let responses: [Response]
    private(set) var requests: [URLRequest] = []

    init(responses: [Response]) {
        self.responses = responses
    }

    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        requests.append(request)
        let response = responses[min(requests.count - 1, responses.count - 1)]
        let statusCode: Int
        let contentType: String
        let body: String
        switch response {
        case .json(let code, let payload):
            statusCode = code
            contentType = "application/json"
            body = payload
        case .sse(let code, let payload):
            statusCode = code
            contentType = "text/event-stream"
            body = payload
        }
        let httpResponse = try #require(HTTPURLResponse(
            url: request.url ?? URL(string: "https://provider.example/v1/chat/completions")!,
            statusCode: statusCode,
            httpVersion: "HTTP/1.1",
            headerFields: ["content-type": contentType]
        ))
        return (Data(body.utf8), httpResponse)
    }
}

private enum TestTransportError: Error, CustomStringConvertible {
    case networkLost

    var description: String {
        "networkLost"
    }
}

private actor ThrowingConformanceTransport: RemoteProviderHTTPTransport {
    private let error: any Error

    init(error: any Error) {
        self.error = error
    }

    func data(for request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        throw error
    }
}

private func runHarness(
    responses: [RecordingConformanceTransport.Response]
) async throws -> OpenAIConformanceReport {
    let transport = RecordingConformanceTransport(responses: responses)
    let harness = OpenAIConformanceHarness(
        target: .realBackendSmoke(
            baseURL: "https://provider.example/v1",
            modelID: "remote-model",
            apiKey: "",
            timeoutSeconds: 30
        ),
        transport: transport
    )
    return try await harness.run()
}

private func row(
    _ field: String,
    in report: OpenAIConformanceReport
) -> OpenAIConformanceRow? {
    report.rows.first { $0.field == field }
}

private func proxyParityTestTarget() -> OpenAIProxyParityTarget {
    OpenAIProxyParityTarget(
        localBaseURL: "https://local.example/v1",
        localModelID: "local-model",
        localAPIKey: "",
        remoteBaseURL: "https://remote.example/v1",
        remoteModelID: "remote-model",
        remoteAPIKey: "",
        timeoutSeconds: 30
    )
}

private func requestBodyModel(_ request: URLRequest) throws -> String? {
    let body = try #require(request.httpBody)
    let object = try #require(try JSONSerialization.jsonObject(with: body) as? [String: Any])
    return object["model"] as? String
}

private func chatCompletionBody() -> String {
    """
    {
      "id": "chatcmpl-test",
      "object": "chat.completion",
      "choices": [
        {
          "index": 0,
          "message": { "role": "assistant", "content": "pong" },
          "finish_reason": "stop"
        }
      ],
      "usage": { "prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5 }
    }
    """
}

private func streamingToolCallBody() -> String {
    """
    data: {"object":"chat.completion.chunk","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call-1","type":"function","function":{"name":"get_weather","arguments":"{\\"city\\":\\"Tokyo\\"}"}}]},"finish_reason":null}]}

    data: {"object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}]}

    data: [DONE]

    """
}

private func streamingToolCallBodyWithJSONWhitespace() -> String {
    """
    data: { "object": "chat.completion.chunk", "choices": [ { "index": 0, "delta": { "tool_calls": [ { "index": 0, "id": "call-1", "type": "function", "function": { "name": "get_weather", "arguments": "{\\"city\\":\\"Tokyo\\"}" } } ] }, "finish_reason": null } ] }

    data: { "object": "chat.completion.chunk", "choices": [ { "index": 0, "delta": {}, "finish_reason": "tool_calls" } ] }

    data: [DONE]

    """
}

private func errorBody(field: String, phase: String) -> String {
    """
    {
      "error": {
        "message": "Unsupported request field",
        "type": "invalid_request_error",
        "code": "unsupported_request_field",
        "field": "\(field)",
        "phase": "\(phase)"
      }
    }
    """
}
