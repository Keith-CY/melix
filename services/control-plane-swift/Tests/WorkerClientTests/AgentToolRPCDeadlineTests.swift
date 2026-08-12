import Foundation
import GRPCCore
import GRPCNIOTransportHTTP2Posix
import NIOPosix
import Testing

@testable import MelixControlPlaneCore
import MelixWorkerProtocol

@Suite("Agent Tool RPC Deadlines", .serialized)
struct AgentToolRPCDeadlineTests {
    @Test("tool RPC deadlines bound catalog execution cancellation and run cleanup")
    func toolRPCDeadlinesBoundEveryAgentToolOperation() async throws {
        let fixture = try await SlowToolRuntimeFixture.start(
            responseDelay: .seconds(1)
        )
        let runner = GRPCPythonWorkerRunner(
            agentToolCancellationTimeoutMilliseconds: 75,
            agentRunCleanupTimeoutMilliseconds: 90
        )

        do {
            try await expectBoundedFailure {
                var request = Melix_Worker_V1_ListAgentToolsRequest()
                request.deadlineUnixMs = unixMillisecondsNow() + 75
                _ = try await runner.listAgentTools(
                    socketPath: fixture.socketPath,
                    request: request
                )
            }

            try await expectBoundedFailure {
                var request = Melix_Worker_V1_ExecuteAgentToolRequest()
                request.context.runID = "run-deadline"
                request.context.deadlineUnixMs = unixMillisecondsNow() + 75
                request.callID = "call-deadline"
                let stream = try await runner.executeAgentTool(
                    socketPath: fixture.socketPath,
                    request: request
                )
                var iterator = stream.makeAsyncIterator()
                _ = try await iterator.next()
            }

            try await expectBoundedFailure {
                var request = Melix_Worker_V1_CancelAgentToolRequest()
                request.runID = "run-deadline"
                request.callID = "call-deadline"
                request.cancellationID = "cancel-deadline"
                _ = try await runner.cancelAgentTool(
                    socketPath: fixture.socketPath,
                    request: request
                )
            }

            try await expectBoundedFailure {
                var request = Melix_Worker_V1_CancelAgentRunToolsRequest()
                request.runID = "run-deadline"
                request.cancellationID = "cancel-run-deadline"
                _ = try await runner.cancelAgentRunTools(
                    socketPath: fixture.socketPath,
                    request: request
                )
            }
        } catch {
            try? await Task.sleep(for: .milliseconds(100))
            await runner.shutdown()
            await fixture.stop()
            throw error
        }

        try? await Task.sleep(for: .milliseconds(100))
        await runner.shutdown()
        await fixture.stop()
    }
}

private func expectBoundedFailure(
    operation: @Sendable () async throws -> Void
) async throws {
    let clock = ContinuousClock()
    let startedAt = clock.now
    var didThrow = false
    do {
        try await operation()
    } catch {
        didThrow = true
    }
    let elapsed = startedAt.duration(to: clock.now)

    #expect(didThrow)
    #expect(elapsed < .milliseconds(500))
}

private func unixMillisecondsNow() -> Int64 {
    Int64(Date().timeIntervalSince1970 * 1_000)
}

private final class SlowToolRuntime: @unchecked Sendable {
    let server: GRPCServer<HTTP2ServerTransport.Posix>
    let serveTask: Task<Void, Error>

    init(
        server: GRPCServer<HTTP2ServerTransport.Posix>,
        serveTask: Task<Void, Error>
    ) {
        self.server = server
        self.serveTask = serveTask
    }
}

private actor SlowToolRuntimeFixture {
    let socketPath: String
    private let eventLoopGroup: MultiThreadedEventLoopGroup
    private var runtime: SlowToolRuntime?

    private init(
        socketPath: String,
        eventLoopGroup: MultiThreadedEventLoopGroup,
        runtime: SlowToolRuntime
    ) {
        self.socketPath = socketPath
        self.eventLoopGroup = eventLoopGroup
        self.runtime = runtime
    }

    static func start(responseDelay: Duration) async throws -> SlowToolRuntimeFixture {
        let socketPath = "/tmp/melix-tool-deadline-\(UUID().uuidString.prefix(8)).sock"
        try? FileManager.default.removeItem(atPath: socketPath)

        let eventLoopGroup = MultiThreadedEventLoopGroup(numberOfThreads: 1)
        let server = GRPCServer(
            transport: .http2NIOPosix(
                address: .unixDomainSocket(path: socketPath),
                transportSecurity: .plaintext,
                eventLoopGroup: eventLoopGroup
            ),
            services: [
                SlowToolRuntimeService(responseDelay: responseDelay),
            ]
        )
        let serveTask = Task {
            try await server.serve()
        }
        _ = try await server.listeningAddress
        return SlowToolRuntimeFixture(
            socketPath: socketPath,
            eventLoopGroup: eventLoopGroup,
            runtime: SlowToolRuntime(server: server, serveTask: serveTask)
        )
    }

    func stop() async {
        if let runtime {
            self.runtime = nil
            runtime.server.beginGracefulShutdown()
            _ = try? await runtime.serveTask.value
        }
        try? await eventLoopGroup.shutdownGracefully()
        try? FileManager.default.removeItem(atPath: socketPath)
    }
}

private final class SlowToolRuntimeService:
    Melix_Worker_V1_ToolRuntimeService.SimpleServiceProtocol,
    @unchecked Sendable
{
    private let responseDelay: Duration

    init(responseDelay: Duration) {
        self.responseDelay = responseDelay
    }

    func listAgentTools(
        request: Melix_Worker_V1_ListAgentToolsRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_ToolCatalogReceipt {
        _ = (request, context)
        try await Task.sleep(for: responseDelay)
        return Melix_Worker_V1_ToolCatalogReceipt()
    }

    func executeAgentTool(
        request: Melix_Worker_V1_ExecuteAgentToolRequest,
        response: RPCWriter<Melix_Worker_V1_AgentToolExecutionEvent>,
        context: ServerContext
    ) async throws {
        _ = (request, response, context)
        try await Task.sleep(for: responseDelay)
    }

    func cancelAgentTool(
        request: Melix_Worker_V1_CancelAgentToolRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_CancelAgentToolResponse {
        _ = (request, context)
        try await Task.sleep(for: responseDelay)
        return Melix_Worker_V1_CancelAgentToolResponse()
    }

    func cancelAgentRunTools(
        request: Melix_Worker_V1_CancelAgentRunToolsRequest,
        context: ServerContext
    ) async throws -> Melix_Worker_V1_CancelAgentRunToolsResponse {
        _ = (request, context)
        try await Task.sleep(for: responseDelay)
        return Melix_Worker_V1_CancelAgentRunToolsResponse()
    }
}
