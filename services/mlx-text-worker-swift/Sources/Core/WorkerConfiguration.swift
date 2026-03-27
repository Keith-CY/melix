import Foundation

package struct WorkerConfiguration: Sendable, Equatable {
    var workerID: String
    var socketPath: String
    var backendMode: String
    var runtimeVersion: String

    init(
        workerID: String = "swift-text-worker-001",
        socketPath: String = "/var/run/melix/swift-text-worker.sock",
        backendMode: String = "swift",
        runtimeVersion: String = "melix-swift-text-worker/dev"
    ) {
        self.workerID = workerID
        self.socketPath = socketPath
        self.backendMode = backendMode
        self.runtimeVersion = runtimeVersion
    }

    package static func fromEnvironment(
        _ environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> WorkerConfiguration {
        WorkerConfiguration(
            workerID: environment["MELIX_SWIFT_TEXT_WORKER_ID"] ?? "swift-text-worker-001",
            socketPath: environment["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"] ?? "/var/run/melix/swift-text-worker.sock",
            backendMode: environment["MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE"] ?? "swift",
            runtimeVersion: environment["MELIX_SWIFT_TEXT_WORKER_RUNTIME_VERSION"] ?? "melix-swift-text-worker/dev"
        )
    }
}
