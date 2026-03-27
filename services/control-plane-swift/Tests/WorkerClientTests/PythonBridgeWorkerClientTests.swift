import Foundation
import SwiftProtobuf
import Testing

@testable import MelixControlPlaneCore
import MelixWorkerProtocol

@Suite("Python Bridge Worker Client")
struct PythonBridgeWorkerClientTests {
    @Test("handshake responses drive dispatch availability")
    func handshakeResponsesDriveDispatchAvailability() async throws {
        var response = Melix_Worker_V1_HandshakeResponse()
        response.protocolVersion = "melix.worker.v1"
        response.runtimeVersion = "dev-runtime"

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .handshake,
            line: bridgeMessageLine(message: try response.serializedData())
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)

        #expect(await client.canDispatchRequests())
    }

    @Test("load model returns the worker handle from the bridge")
    func loadModelReturnsWorkerHandle() async throws {
        var request = Melix_Worker_V1_LoadModelRequest()
        request.model = devModel()
        request.pinOnLoad = true

        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "melix-dev-text::bridge"

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .loadModel,
            line: bridgeMessageLine(message: try response.serializedData())
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let loaded = try await client.loadModel(request: request)

        #expect(loaded.ok)
        #expect(loaded.modelHandle == "melix-dev-text::bridge")
    }

    @Test("generate decodes streamed execute events from the bridge")
    func generateDecodesStreamedExecuteEventsFromTheBridge() async throws {
        var request = Melix_Worker_V1_GenerateRequest()
        request.execution.id.requestID = "req-bridge"
        request.execution.modelHandle = "melix-dev-text::bridge"

        let runner = ScriptedBridgeRunner()
        await runner.setStreamResponse(
            .generate,
            lines: [
                bridgeMessageLine(message: try makeTokenEvent(requestID: "req-bridge", seq: 1, text: "Echo").serializedData()),
                bridgeMessageLine(message: try makeCompletedEvent(requestID: "req-bridge", seq: 2, finishReason: "stop", assistantText: "Echo").serializedData()),
            ]
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let stream = try await client.generate(request: request)
        let events = try await collect(stream)

        #expect(events.count == 2)
        #expect(events[0].tokenDelta.text == "Echo")
        #expect(events[1].completed.finishReason == "stop")
    }

    @Test("abort returns the found bit from the bridge response")
    func abortReturnsFoundBitFromTheBridgeResponse() async throws {
        var response = Melix_Worker_V1_AbortResponse()
        response.ok = true
        response.found = true

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .abort,
            line: bridgeMessageLine(message: try response.serializedData())
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let aborted = try await client.abort(requestID: "req-abort")

        #expect(aborted)
    }

    @Test("bootstrap preload writes the worker handle into the model catalog")
    func bootstrapPreloadWritesTheWorkerHandleIntoTheModelCatalog() async throws {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "melix-dev-text::bridge"

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .loadModel,
            line: bridgeMessageLine(message: try response.serializedData())
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let catalog = ModelCatalog()

        let preloaded = try await BootstrapWorkerPreparation.preloadDevTextModel(
            workerClient: client,
            modelCatalog: catalog
        )

        #expect(preloaded)
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == "melix-dev-text::bridge")
    }

    @Test("bridge client treats helper errors as unavailable")
    func bridgeClientTreatsHelperErrorsAsUnavailable() async throws {
        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(.handshake, line: bridgeErrorLine(code: "UNAVAILABLE", message: "worker down"))
        await runner.setStreamResponse(
            .generate,
            lines: [#"{"kind":"message","message_b64":"%%%"}"#]
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)

        #expect(!(await client.canDispatchRequests()))

        var request = Melix_Worker_V1_GenerateRequest()
        request.execution.id.requestID = "req-bad"
        request.execution.modelHandle = "melix-dev-text::bridge"

        do {
            let stream = try await client.generate(request: request)
            _ = try await collect(stream)
            Issue.record("Expected the malformed bridge payload to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .unavailable)
        }
    }

    @Test("bootstrap preload returns false when the worker does not hand back a handle")
    func bootstrapPreloadReturnsFalseWithoutAHandle() async throws {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = false

        let runner = ScriptedBridgeRunner()
        await runner.setUnaryResponse(
            .loadModel,
            line: bridgeMessageLine(message: try response.serializedData())
        )

        let client = PythonBridgeWorkerClient(socketPath: "/tmp/melix-test.sock", runner: runner)
        let catalog = ModelCatalog()
        let preloaded = try await BootstrapWorkerPreparation.preloadDevTextModel(
            workerClient: client,
            modelCatalog: catalog
        )

        #expect(!preloaded)
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == nil)
    }

    @Test("process bridge runner executes unary, stream, and failure paths")
    func processBridgeRunnerExecutesUnaryStreamAndFailurePaths() async throws {
        let fixtureRoot = try makeProcessBridgeFixtureRepo()
        let runner = ProcessWorkerBridgeRunner(
            repoRoot: fixtureRoot.path,
            environment: ProcessInfo.processInfo.environment
        )

        let unaryLine = try await runner.runUnary(
            command: BridgeCommand(kind: .handshake, socketPath: "/tmp/unused.sock", requestData: Data("hello".utf8))
        )
        #expect(unaryLine.contains("\"kind\""))

        let stream = try await runner.runStream(
            command: BridgeCommand(kind: .generate, socketPath: "/tmp/unused.sock", requestData: Data("stream".utf8))
        )
        let lines = try await collect(stream)
        #expect(lines.count == 2)

        do {
            _ = try await runner.runUnary(
                command: BridgeCommand(kind: .abort, socketPath: "/tmp/unused.sock", requestData: Data())
            )
            Issue.record("Expected the abort fixture to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .unavailable)
        }
    }

    private func devModel() -> Melix_Worker_V1_ModelSpec {
        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = "melix-dev-text"
        model.modelPath = "models/melix-dev-text"
        model.modelKind = "text"
        model.revision = "dev"
        model.tokenizerHash = "tok-dev"
        model.quantProfileID = "q4"
        model.parserMode = "text"
        model.reasoningMode = "off"
        model.maxContext = 8192
        return model
    }
}

private actor ScriptedBridgeRunner: WorkerBridgeRunning {
    private var unary: [BridgeCommandKind: String] = [:]
    private var streams: [BridgeCommandKind: [String]] = [:]

    func setUnaryResponse(_ kind: BridgeCommandKind, line: String) {
        unary[kind] = line
    }

    func setStreamResponse(_ kind: BridgeCommandKind, lines: [String]) {
        streams[kind] = lines
    }

    func runUnary(command: BridgeCommand) async throws -> String {
        unary[command.kind] ?? bridgeErrorLine(code: "missing_fixture", message: "No unary fixture.")
    }

    func runStream(command: BridgeCommand) async throws -> AsyncThrowingStream<String, Error> {
        let lines = streams[command.kind] ?? []
        return AsyncThrowingStream { continuation in
            for line in lines {
                continuation.yield(line)
            }
            continuation.finish()
        }
    }
}

private func bridgeMessageLine(message: Data) -> String {
    let payload = ["kind": "message", "message_b64": message.base64EncodedString()]
    let data = try! JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    return String(decoding: data, as: UTF8.self)
}

private func bridgeErrorLine(code: String, message: String) -> String {
    let payload = [
        "kind": "error",
        "code": code,
        "message": message,
    ]
    let data = try! JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    return String(decoding: data, as: UTF8.self)
}

private func makeProcessBridgeFixtureRepo() throws -> URL {
    let root = FileManager.default.temporaryDirectory
        .appendingPathComponent("melix-bridge-fixture-\(UUID().uuidString)", isDirectory: true)
    let workerDir = root.appendingPathComponent("services/mlx-worker-python/worker", isDirectory: true)
    try FileManager.default.createDirectory(at: workerDir, withIntermediateDirectories: true)
    try """
    [project]
    name = "fixture-worker"
    version = "0.1.0"
    requires-python = ">=3.12"
    dependencies = []
    """.write(
        to: root.appendingPathComponent("services/mlx-worker-python/pyproject.toml"),
        atomically: true,
        encoding: .utf8
    )
    try """
    import argparse
    import base64
    import json
    import sys
    import time

    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--socket-path", required=True)
    parser.add_argument("--request-b64", required=True)
    args = parser.parse_args()

    if args.command == "abort":
        sys.exit(1)

    if args.command == "generate":
        print(json.dumps({"kind": "message", "message_b64": base64.b64encode(b"first").decode("ascii")}), flush=True)
        time.sleep(0.01)
        print(json.dumps({"kind": "message", "message_b64": base64.b64encode(b"second").decode("ascii")}), flush=True)
    else:
        print(json.dumps({"kind": "message", "message_b64": base64.b64encode(b"ok").decode("ascii")}), flush=True)
    """.write(
        to: workerDir.appendingPathComponent("control_plane_bridge.py"),
        atomically: true,
        encoding: .utf8
    )
    return root
}

private func makeTokenEvent(
    requestID: String,
    seq: UInt64,
    text: String
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = "generate"
    event.seq = seq
    event.tokenDelta = Melix_Worker_V1_TokenDelta()
    event.tokenDelta.text = text
    return event
}

private func makeCompletedEvent(
    requestID: String,
    seq: UInt64,
    finishReason: String,
    assistantText: String
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.executionKind = "generate"
    event.seq = seq
    event.completed = Melix_Worker_V1_Completed()
    event.completed.finishReason = finishReason
    event.completed.assistantText = assistantText
    return event
}

private func collect<T: Sendable>(_ stream: AsyncThrowingStream<T, Error>) async throws -> [T] {
    var values: [T] = []
    for try await value in stream {
        values.append(value)
    }
    return values
}
