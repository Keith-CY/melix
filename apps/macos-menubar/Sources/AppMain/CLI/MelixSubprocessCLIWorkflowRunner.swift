import Foundation
import MelixCLICore

public actor MelixSubprocessCLIWorkflowRunner: MelixCLIWorkflowRunning {
    private let cliExecutablePath: String
    private let environment: [String: String]
    private let processExecutor: any MelixCLIProcessExecuting

    public init(
        cliExecutablePath: String,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        processExecutor: any MelixCLIProcessExecuting = LiveMelixCLIProcessExecutor()
    ) {
        self.cliExecutablePath = cliExecutablePath
        self.environment = environment
        self.processExecutor = processExecutor
    }

    public nonisolated var surface: MelixCLIWorkflowSurface {
        .subprocess
    }

    public func run(_ command: MelixCLICommand) async throws -> String {
        let arguments = try arguments(for: command)
        do {
            return try await processExecutor.run(
                executablePath: cliExecutablePath,
                arguments: arguments,
                environment: environment
            )
        } catch let error as MelixCLIProcessExecutionError {
            switch error {
            case .nonZeroExit(_, _, let exitCode, let stderr):
                throw MelixCLIWorkflowError.processFailed(
                    commandID: command.workflowCommandID,
                    surface: .subprocess,
                    exitCode: exitCode,
                    stderr: stderr
                )
            case .launchFailed(_, let reason), .invalidOutput(_, let reason):
                throw MelixCLIWorkflowError.processFailed(
                    commandID: command.workflowCommandID,
                    surface: .subprocess,
                    exitCode: 1,
                    stderr: reason
                )
            }
        }
    }

    private func arguments(for command: MelixCLICommand) throws -> [String] {
        do {
            return try MelixCLICommandCodec.arguments(for: command)
        } catch {
            throw MelixCLIWorkflowError.unsupportedCommand(
                commandID: command.workflowCommandID,
                surface: .subprocess
            )
        }
    }
}
