import Darwin
import Foundation

public enum ControlPlaneHomeOwnershipError: Error, Equatable, Sendable {
    case unsafePath(String)
    case alreadyOwned(String)
    case systemCall(String)
}

extension ControlPlaneHomeOwnershipError: LocalizedError {
    public var errorDescription: String? {
        switch self {
        case let .unsafePath(message),
             let .alreadyOwned(message),
             let .systemCall(message):
            message
        }
    }
}

/// Process-lifetime, fail-fast single-writer lease for MELIX_HOME. The token is
/// persisted while the advisory lock is held and also becomes the daemon
/// instance ID, so clients can detect a new writer generation after restart.
public final class ControlPlaneHomeOwnershipLease: @unchecked Sendable {
    public let fencingToken: String
    public let lockPath: String

    private let stateLock = NSLock()
    private var descriptor: Int32?

    private init(descriptor: Int32, fencingToken: String, lockPath: String) {
        self.descriptor = descriptor
        self.fencingToken = fencingToken
        self.lockPath = lockPath
    }

    public static func acquire(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default,
        fencingToken: String = UUID().uuidString.lowercased()
    ) throws -> ControlPlaneHomeOwnershipLease {
        let stateDirectory = MelixPathLayout(environment: environment).stateDirectoryURL
        try fileManager.createDirectory(
            at: stateDirectory,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: NSNumber(value: 0o700)]
        )
        var directoryStatus = stat()
        guard lstat(stateDirectory.path, &directoryStatus) == 0,
              directoryStatus.st_mode & mode_t(S_IFMT) == S_IFDIR,
              directoryStatus.st_uid == geteuid()
        else {
            throw ControlPlaneHomeOwnershipError.unsafePath(
                "MELIX_HOME state directory must be a current-user directory."
            )
        }
        if directoryStatus.st_mode & 0o077 != 0 {
            guard chmod(stateDirectory.path, 0o700) == 0 else {
                throw posixError("Could not make the MELIX_HOME state directory private")
            }
        }

        let lockURL = stateDirectory.appendingPathComponent(
            "control-plane-writer.lock",
            isDirectory: false
        )
        let descriptor = lockURL.withUnsafeFileSystemRepresentation { path -> Int32 in
            guard let path else {
                errno = EINVAL
                return -1
            }
            return Darwin.open(
                path,
                O_CREAT | O_RDWR | O_CLOEXEC | O_NOFOLLOW | O_EXLOCK | O_NONBLOCK,
                mode_t(S_IRUSR | S_IWUSR)
            )
        }
        guard descriptor >= 0 else {
            if errno == EWOULDBLOCK || errno == EAGAIN {
                throw ControlPlaneHomeOwnershipError.alreadyOwned(
                    "Another Melix control plane already owns this MELIX_HOME."
                )
            }
            throw posixError("Could not acquire the MELIX_HOME writer lease")
        }
        do {
            var fileStatus = stat()
            guard fstat(descriptor, &fileStatus) == 0 else {
                throw posixError("Could not inspect the MELIX_HOME writer lease")
            }
            guard fileStatus.st_mode & mode_t(S_IFMT) == S_IFREG,
                  fileStatus.st_uid == geteuid()
            else {
                throw ControlPlaneHomeOwnershipError.unsafePath(
                    "MELIX_HOME writer lease must be a current-user regular file."
                )
            }
            guard fchmod(descriptor, mode_t(S_IRUSR | S_IWUSR)) == 0,
                  ftruncate(descriptor, 0) == 0,
                  lseek(descriptor, 0, SEEK_SET) >= 0
            else {
                throw posixError("Could not initialize the MELIX_HOME writer lease")
            }
            let payload = Data("\(fencingToken)\n".utf8)
            try payload.withUnsafeBytes { buffer in
                guard let baseAddress = buffer.baseAddress else { return }
                var offset = 0
                while offset < buffer.count {
                    let written = Darwin.write(
                        descriptor,
                        baseAddress.advanced(by: offset),
                        buffer.count - offset
                    )
                    guard written > 0 else {
                        throw posixError("Could not persist the MELIX_HOME fencing token")
                    }
                    offset += written
                }
            }
            guard fsync(descriptor) == 0 else {
                throw posixError("Could not flush the MELIX_HOME fencing token")
            }
            return ControlPlaneHomeOwnershipLease(
                descriptor: descriptor,
                fencingToken: fencingToken,
                lockPath: lockURL.path
            )
        } catch {
            _ = Darwin.close(descriptor)
            throw error
        }
    }

    public func release() {
        stateLock.lock()
        let descriptor = self.descriptor
        self.descriptor = nil
        stateLock.unlock()
        if let descriptor {
            _ = Darwin.close(descriptor)
        }
    }

    deinit {
        release()
    }
}

private func posixError(_ operation: String) -> ControlPlaneHomeOwnershipError {
    .systemCall("\(operation): \(String(cString: strerror(errno)))")
}
