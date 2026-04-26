import Foundation

#if canImport(MLX)
@preconcurrency import MLX
#endif

final class DFlashSpeculativeProbeLogger: @unchecked Sendable {
    static let enabledEnvironmentKey = "MELIX_SWIFT_DFLASH_PROBE"
    static let pathEnvironmentKey = "MELIX_SWIFT_DFLASH_PROBE_PATH"
    static let defaultFilename = "swift-dflash-probe.jsonl"

    let fileURL: URL

    private let lock = NSLock()
    private let sessionID: String
    private let startedAt: Date

    init(fileURL: URL, sessionID: String = UUID().uuidString, startedAt: Date = Date()) throws {
        self.fileURL = fileURL
        self.sessionID = sessionID
        self.startedAt = startedAt

        try FileManager.default.createDirectory(
            at: fileURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        if !FileManager.default.fileExists(atPath: fileURL.path) {
            FileManager.default.createFile(atPath: fileURL.path, contents: nil)
        }
    }

    static func fromEnvironment(
        _ environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> DFlashSpeculativeProbeLogger? {
        guard shouldEnable(environment: environment),
              let fileURL = resolvedProbeURL(environment: environment) else {
            return nil
        }
        return try? DFlashSpeculativeProbeLogger(fileURL: fileURL)
    }

    static func shouldEnable(environment: [String: String]) -> Bool {
        if let path = environment[pathEnvironmentKey], !path.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return true
        }
        return isTruthy(environment[enabledEnvironmentKey])
    }

    static func resolvedProbeURL(environment: [String: String]) -> URL? {
        if let rawPath = environment[pathEnvironmentKey]?.trimmingCharacters(in: .whitespacesAndNewlines),
           !rawPath.isEmpty {
            return URL(fileURLWithPath: rawPath)
        }
        if let runtimeDirectory = environment["MELIX_RUNTIME_DIR"]?.trimmingCharacters(in: .whitespacesAndNewlines),
           !runtimeDirectory.isEmpty {
            return URL(fileURLWithPath: runtimeDirectory).appendingPathComponent(defaultFilename)
        }
        return FileManager.default.temporaryDirectory.appendingPathComponent(defaultFilename)
    }

    func record(stage: String, fields: [String: Any] = [:]) {
        var payload = fields
        payload["schema_version"] = 1
        payload["session_id"] = sessionID
        payload["stage"] = stage
        payload["elapsed_ms"] = max(0, Int(Date().timeIntervalSince(startedAt) * 1000))
        payload["pid"] = Int(ProcessInfo.processInfo.processIdentifier)

        guard JSONSerialization.isValidJSONObject(payload),
              let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]) else {
            return
        }

        var line = data
        line.append(0x0A)

        lock.lock()
        defer { lock.unlock() }

        guard let handle = try? FileHandle(forWritingTo: fileURL) else {
            return
        }
        defer {
            try? handle.close()
        }
        _ = try? handle.seekToEnd()
        _ = try? handle.write(contentsOf: line)
    }

    private static func isTruthy(_ rawValue: String?) -> Bool {
        switch rawValue?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "1", "true", "yes", "on":
            return true
        default:
            return false
        }
    }
}

func dflashTokenIDPreview(_ tokenIDs: [Int], edgeCount: Int = 8) -> [String: Any] {
    [
        "count": tokenIDs.count,
        "head": Array(tokenIDs.prefix(edgeCount)),
        "tail": Array(tokenIDs.suffix(edgeCount)),
    ]
}

#if canImport(MLX)
func dflashArrayDescriptor(_ array: MLXArray) -> [String: Any] {
    [
        "shape": array.shape,
        "dtype": String(describing: array.dtype),
    ]
}
#endif
