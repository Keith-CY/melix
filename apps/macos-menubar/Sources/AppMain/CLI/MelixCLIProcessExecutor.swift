import Foundation

public enum MelixCLIProcessExecutionError: Error, Equatable, Sendable, LocalizedError {
    case launchFailed(executablePath: String, reason: String)
    case nonZeroExit(executablePath: String, arguments: [String], exitCode: Int32, stderr: String)
    case invalidOutput(executablePath: String, reason: String)

    public var errorDescription: String? {
        switch self {
        case .launchFailed(let executablePath, let reason):
            return "Failed to launch \(executablePath): \(reason)"
        case .nonZeroExit(let executablePath, _, let exitCode, let stderr):
            let detail = stderr.trimmingCharacters(in: .whitespacesAndNewlines)
            return detail.isEmpty
                ? "\(executablePath) exited with code \(exitCode)."
                : "\(executablePath) exited with code \(exitCode): \(detail)"
        case .invalidOutput(let executablePath, let reason):
            return "Invalid output from \(executablePath): \(reason)"
        }
    }
}

public protocol MelixCLIProcessExecuting: Sendable {
    func run(
        executablePath: String,
        arguments: [String],
        environment: [String: String]
    ) async throws -> String
}

public struct LiveMelixCLIProcessExecutor: MelixCLIProcessExecuting {
    public init() {}

    public func run(
        executablePath: String,
        arguments: [String],
        environment: [String: String]
    ) async throws -> String {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executablePath)
        process.arguments = arguments
        process.environment = environment

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        let stdoutTask = Task.detached(priority: .userInitiated) { () throws -> Data in
            try stdoutPipe.fileHandleForReading.readToEnd() ?? Data()
        }
        let stderrTask = Task.detached(priority: .userInitiated) { () throws -> Data in
            try stderrPipe.fileHandleForReading.readToEnd() ?? Data()
        }

        do {
            try process.run()
        } catch {
            stdoutTask.cancel()
            stderrTask.cancel()
            throw MelixCLIProcessExecutionError.launchFailed(
                executablePath: executablePath,
                reason: String(describing: error)
            )
        }

        process.waitUntilExit()

        let stdoutData = try await stdoutTask.value
        let stderrData = try await stderrTask.value
        let stdout = String(decoding: stdoutData, as: UTF8.self)
        let stderr = String(decoding: stderrData, as: UTF8.self)

        guard process.terminationStatus == 0 else {
            throw MelixCLIProcessExecutionError.nonZeroExit(
                executablePath: executablePath,
                arguments: arguments,
                exitCode: process.terminationStatus,
                stderr: stderr
            )
        }

        return stdout
    }
}
