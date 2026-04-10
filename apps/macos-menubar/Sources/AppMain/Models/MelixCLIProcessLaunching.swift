import Foundation

public struct MelixCLIProcessResult: Equatable, Sendable {
    public let stdout: String
    public let stderr: String
    public let exitStatus: Int32

    public init(stdout: String, stderr: String, exitStatus: Int32) {
        self.stdout = stdout
        self.stderr = stderr
        self.exitStatus = exitStatus
    }
}

public protocol MelixCLIProcessLaunching: Sendable {
    func run(executable: String, arguments: [String], environment: [String: String]) async throws -> MelixCLIProcessResult
}

public struct FoundationMelixCLIProcessLauncher: MelixCLIProcessLaunching {
    public init() {}

    public func run(
        executable: String,
        arguments: [String],
        environment: [String: String]
    ) async throws -> MelixCLIProcessResult {
        try await withCheckedThrowingContinuation { continuation in
            let process = Process()
            let stdout = Pipe()
            let stderr = Pipe()
            let stdoutBuffer = ProcessOutputBuffer()
            let stderrBuffer = ProcessOutputBuffer()
            let completion = ProcessLaunchCompletion(continuation: continuation)

            process.executableURL = URL(fileURLWithPath: executable)
            process.arguments = arguments
            process.environment = environment
            process.standardOutput = stdout
            process.standardError = stderr

            stdout.fileHandleForReading.readabilityHandler = { handle in
                let data = handle.availableData
                if data.isEmpty {
                    handle.readabilityHandler = nil
                    return
                }
                stdoutBuffer.append(data)
            }
            stderr.fileHandleForReading.readabilityHandler = { handle in
                let data = handle.availableData
                if data.isEmpty {
                    handle.readabilityHandler = nil
                    return
                }
                stderrBuffer.append(data)
            }

            process.terminationHandler = { process in
                stdout.fileHandleForReading.readabilityHandler = nil
                stderr.fileHandleForReading.readabilityHandler = nil
                stdoutBuffer.appendRemaining(from: stdout.fileHandleForReading)
                stderrBuffer.appendRemaining(from: stderr.fileHandleForReading)
                completion.resume(
                    returning: MelixCLIProcessResult(
                        stdout: String(decoding: stdoutBuffer.data, as: UTF8.self),
                        stderr: String(decoding: stderrBuffer.data, as: UTF8.self),
                        exitStatus: process.terminationStatus
                    )
                )
            }

            do {
                try process.run()
            } catch {
                stdout.fileHandleForReading.readabilityHandler = nil
                stderr.fileHandleForReading.readabilityHandler = nil
                completion.resume(throwing: error)
            }
        }
    }
}

private final class ProcessOutputBuffer: @unchecked Sendable {
    private let lock = NSLock()
    private var storage = Data()

    func append(_ data: Data) {
        guard data.isEmpty == false else {
            return
        }
        lock.lock()
        storage.append(data)
        lock.unlock()
    }

    func appendRemaining(from fileHandle: FileHandle) {
        while true {
            let data = fileHandle.availableData
            if data.isEmpty {
                break
            }
            append(data)
        }
    }

    var data: Data {
        lock.lock()
        defer { lock.unlock() }
        return storage
    }
}

private final class ProcessLaunchCompletion: @unchecked Sendable {
    private let lock = NSLock()
    private var continuation: CheckedContinuation<MelixCLIProcessResult, Error>?

    init(continuation: CheckedContinuation<MelixCLIProcessResult, Error>) {
        self.continuation = continuation
    }

    func resume(returning result: MelixCLIProcessResult) {
        lock.lock()
        let continuation = self.continuation
        self.continuation = nil
        lock.unlock()
        continuation?.resume(returning: result)
    }

    func resume(throwing error: Error) {
        lock.lock()
        let continuation = self.continuation
        self.continuation = nil
        lock.unlock()
        continuation?.resume(throwing: error)
    }
}
