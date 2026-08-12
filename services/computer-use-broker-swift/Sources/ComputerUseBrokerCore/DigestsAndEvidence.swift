import CryptoKit
import Darwin
import Foundation

public enum ComputerUseArtifactSecurity {
    public static func ensurePrivateDirectory(_ url: URL) throws {
        try FileManager.default.createDirectory(
            at: url,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: NSNumber(value: 0o700)]
        )
        try FileManager.default.setAttributes(
            [.posixPermissions: NSNumber(value: 0o700)],
            ofItemAtPath: url.path
        )
    }

    public static func protectPrivateFile(_ url: URL) throws {
        try FileManager.default.setAttributes(
            [.posixPermissions: NSNumber(value: 0o600)],
            ofItemAtPath: url.path
        )
    }
}

public enum ComputerActionDigest {
    private struct Payload: Codable {
        let schemaVersion: String
        let sessionID: String
        let actionID: String
        let idempotencyKey: String
        let target: ComputerWindowTarget
        let expectedFrameID: String
        let expectedFrameGeneration: UInt64
        let action: ComputerAction
    }

    public static func compute(
        sessionID: String,
        actionID: String,
        idempotencyKey: String,
        target: ComputerWindowTarget,
        expectedFrameID: String,
        expectedFrameGeneration: UInt64,
        action: ComputerAction
    ) throws -> String {
        let payload = Payload(
            schemaVersion: "melix.computer_action.v1",
            sessionID: sessionID,
            actionID: actionID,
            idempotencyKey: idempotencyKey,
            target: target,
            expectedFrameID: expectedFrameID,
            expectedFrameGeneration: expectedFrameGeneration,
            action: action
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return sha256Hex(try encoder.encode(payload))
    }

    public static func compute(for request: PerformComputerActionRequest) throws -> String {
        try compute(
            sessionID: request.sessionID,
            actionID: request.actionID,
            idempotencyKey: request.idempotencyKey,
            target: request.target,
            expectedFrameID: request.expectedFrameID,
            expectedFrameGeneration: request.expectedFrameGeneration,
            action: request.action
        )
    }
}

public struct FileComputerUseEvidenceSink: ComputerUseEvidenceSink {
    public init() {}

    public func record(
        _ receipt: ComputerActionReceipt,
        in artifactDirectory: URL
    ) throws -> ComputerArtifactReference {
        try ComputerUseArtifactSecurity.ensurePrivateDirectory(
            artifactDirectory
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        encoder.dateEncodingStrategy = .iso8601
        let data = try encoder.encode(receipt)
        let safeActionID = sanitizedArtifactComponent(receipt.actionID)
        let actionIDDigest = sha256Hex(Data(receipt.actionID.utf8))
        let artifactID = "action-receipt-\(safeActionID)-\(actionIDDigest)"
        let url = artifactDirectory.appendingPathComponent(
            "\(artifactID).json",
            isDirectory: false
        )
        try writeExclusivePrivateFile(data, to: url)
        return ComputerArtifactReference(
            artifactID: artifactID,
            path: url.path,
            sha256: sha256Hex(data),
            byteCount: data.count,
            mediaType: "application/json",
            adapterKind: "file-evidence-v1"
        )
    }
}

public struct FileComputerUseActionJournal: ComputerUseActionJournal {
    public init() {}

    public func record(
        _ boundary: ComputerActionBoundaryRecord,
        in artifactDirectory: URL
    ) throws -> ComputerArtifactReference {
        try ComputerUseArtifactSecurity.ensurePrivateDirectory(artifactDirectory)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        encoder.dateEncodingStrategy = .iso8601
        let data = try encoder.encode(boundary)
        let safeActionID = sanitizedArtifactComponent(boundary.actionID)
        let actionIDDigest = sha256Hex(Data(boundary.actionID.utf8))
        let artifactID = [
            "action-boundary",
            boundary.phase.rawValue,
            safeActionID,
            actionIDDigest,
        ].joined(separator: "-")
        let url = artifactDirectory.appendingPathComponent(
            "\(artifactID).json",
            isDirectory: false
        )
        try writeExclusivePrivateFile(data, to: url)
        return ComputerArtifactReference(
            artifactID: artifactID,
            path: url.path,
            sha256: sha256Hex(data),
            byteCount: data.count,
            mediaType: "application/json",
            adapterKind: "file-action-journal-v1"
        )
    }
}

func sha256Hex(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

private func sanitizedArtifactComponent(_ value: String) -> String {
    let normalized = value.unicodeScalars.map { scalar -> Character in
        let allowed = CharacterSet.alphanumerics.contains(scalar)
            || scalar == "-" || scalar == "_"
        return allowed ? Character(String(scalar)) : "_"
    }
    let result = String(normalized).prefix(48)
    return result.isEmpty ? "unknown" : String(result)
}

private func writeExclusivePrivateFile(_ data: Data, to url: URL) throws {
    let descriptor = url.withUnsafeFileSystemRepresentation { path -> Int32 in
        guard let path else {
            errno = EINVAL
            return -1
        }
        return Darwin.open(
            path,
            O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
            mode_t(S_IRUSR | S_IWUSR)
        )
    }
    guard descriptor >= 0 else {
        throw exclusiveWriteError(
            "Could not exclusively create Computer Use evidence",
            url: url
        )
    }

    var completed = false
    defer {
        _ = Darwin.close(descriptor)
        if !completed {
            _ = Darwin.unlink(url.path)
        }
    }
    try data.withUnsafeBytes { bytes in
        guard let baseAddress = bytes.baseAddress else { return }
        var offset = 0
        while offset < bytes.count {
            let written = Darwin.write(
                descriptor,
                baseAddress.advanced(by: offset),
                bytes.count - offset
            )
            if written < 0, errno == EINTR {
                continue
            }
            guard written > 0 else {
                throw exclusiveWriteError(
                    "Could not persist Computer Use evidence",
                    url: url
                )
            }
            offset += written
        }
    }
    guard Darwin.fsync(descriptor) == 0 else {
        throw exclusiveWriteError("Could not flush Computer Use evidence", url: url)
    }
#if os(macOS)
    guard Darwin.fcntl(descriptor, F_FULLFSYNC) == 0 else {
        throw exclusiveWriteError(
            "Could not fully flush Computer Use evidence",
            url: url
        )
    }
#endif
    try syncDirectoryEntry(containing: url)
    completed = true
}

private func syncDirectoryEntry(containing url: URL) throws {
    let directory = url.deletingLastPathComponent()
    let descriptor = directory.withUnsafeFileSystemRepresentation { path -> Int32 in
        guard let path else {
            errno = EINVAL
            return -1
        }
        return Darwin.open(
            path,
            O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW
        )
    }
    guard descriptor >= 0 else {
        throw exclusiveWriteError(
            "Could not open Computer Use evidence directory for flush",
            url: directory
        )
    }
    defer { _ = Darwin.close(descriptor) }
    guard Darwin.fsync(descriptor) == 0 else {
        throw exclusiveWriteError(
            "Could not flush Computer Use evidence directory",
            url: directory
        )
    }
}

private func exclusiveWriteError(_ operation: String, url: URL) -> NSError {
    NSError(
        domain: NSPOSIXErrorDomain,
        code: Int(errno),
        userInfo: [
            NSLocalizedDescriptionKey: "\(operation): \(String(cString: strerror(errno)))",
            NSFilePathErrorKey: url.path,
        ]
    )
}
