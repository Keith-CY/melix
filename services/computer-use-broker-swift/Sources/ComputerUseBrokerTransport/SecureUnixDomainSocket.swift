import Darwin
import Foundation
import GRPCCore
import GRPCNIOTransportHTTP2Posix

public enum SecureUnixDomainSocketError: Error, Sendable, Equatable {
    case invalidPath(String)
    case unsafePermissions(String)
    case invalidOwner(String)
    case unexpectedFileType(String)
    case alreadyInUse(String)
    case systemCall(String)
}

extension SecureUnixDomainSocketError: LocalizedError {
    public var errorDescription: String? {
        switch self {
        case let .invalidPath(message),
             let .unsafePermissions(message),
             let .invalidOwner(message),
             let .unexpectedFileType(message),
             let .alreadyInUse(message),
             let .systemCall(message):
            message
        }
    }
}

public final class SecureUnixDomainSocketPath: @unchecked Sendable, Equatable {
    public let path: String

    private let stateLock = NSLock()
    private var leaseDescriptor: Int32?
    private var boundIdentity: SocketFileIdentity?
    private var stagedReplacementPath: String?

    private var parentPath: String {
        URL(fileURLWithPath: path).deletingLastPathComponent().path
    }

    public init(path: String) throws {
        let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.hasPrefix("/"), !trimmed.isEmpty else {
            throw SecureUnixDomainSocketError.invalidPath(
                "Computer Use socket path must be absolute."
            )
        }
        let standardized = URL(fileURLWithPath: trimmed).standardizedFileURL.path
        guard standardized == trimmed else {
            throw SecureUnixDomainSocketError.invalidPath(
                "Computer Use socket path must already be standardized."
            )
        }
        let leaf = URL(fileURLWithPath: trimmed).lastPathComponent
        guard trimmed != "/", !leaf.isEmpty, leaf != ".", leaf != ".." else {
            throw SecureUnixDomainSocketError.invalidPath(
                "Computer Use socket path must include a file name."
            )
        }
        // `sockaddr_un.sun_path` is 104 bytes on macOS including the NUL.
        guard trimmed.utf8.count <= 103 else {
            throw SecureUnixDomainSocketError.invalidPath(
                "Computer Use socket path exceeds the macOS Unix-domain socket limit."
            )
        }
        self.path = trimmed
    }

    public static func == (
        lhs: SecureUnixDomainSocketPath,
        rhs: SecureUnixDomainSocketPath
    ) -> Bool {
        lhs.path == rhs.path
    }

    public func prepareForBinding() throws {
        stateLock.lock()
        defer { stateLock.unlock() }
        guard leaseDescriptor == nil, boundIdentity == nil else {
            throw SecureUnixDomainSocketError.alreadyInUse(
                "Computer Use socket lifecycle already owns this endpoint."
            )
        }
        let parentURL = URL(fileURLWithPath: parentPath, isDirectory: true)
        if !FileManager.default.fileExists(atPath: parentPath) {
            do {
                try FileManager.default.createDirectory(
                    at: parentURL,
                    withIntermediateDirectories: true,
                    attributes: [.posixPermissions: NSNumber(value: 0o700)]
                )
            } catch {
                throw SecureUnixDomainSocketError.systemCall(
                    "Could not create the private socket directory: \(error.localizedDescription)"
                )
            }
        }
        let parent = try fileStatus(at: parentPath)
        guard fileType(parent) == S_IFDIR else {
            throw SecureUnixDomainSocketError.unexpectedFileType(
                "Computer Use socket parent must be a directory."
            )
        }
        try validateOwner(parent, path: parentPath)
        try validatePrivatePermissions(parent, path: parentPath)

        let descriptor = try acquireSocketLease(at: path + ".lock")
        do {
            if let existing = try optionalFileStatus(at: path) {
                guard fileType(existing) == S_IFSOCK else {
                    throw SecureUnixDomainSocketError.unexpectedFileType(
                        "Computer Use refuses to replace a non-socket path."
                    )
                }
                try validateOwner(existing, path: path)
                try validatePrivatePermissions(existing, path: path)
                let existingIdentity = SocketFileIdentity(existing)
                if try unixDomainSocketIsLive(path: path) {
                    throw SecureUnixDomainSocketError.alreadyInUse(
                        "Another Computer Use broker is already listening on this socket."
                    )
                }
                if let current = try optionalFileStatus(at: path) {
                    guard SocketFileIdentity(current) == existingIdentity else {
                        throw SecureUnixDomainSocketError.alreadyInUse(
                            "Computer Use socket changed during stale-endpoint recovery."
                        )
                    }
                    guard unlink(path) == 0 else {
                        throw posixFailure("Could not remove the stale Computer Use socket")
                    }
                }
            }
            leaseDescriptor = descriptor
        } catch {
            _ = Darwin.close(descriptor)
            throw error
        }
    }

    public func sealBoundSocket() throws {
        stateLock.lock()
        defer { stateLock.unlock() }
        guard leaseDescriptor != nil else {
            throw SecureUnixDomainSocketError.systemCall(
                "Computer Use socket lifecycle does not hold its startup lease."
            )
        }
        let existing = try fileStatus(at: path)
        guard fileType(existing) == S_IFSOCK else {
            throw SecureUnixDomainSocketError.unexpectedFileType(
                "Computer Use transport did not create a Unix-domain socket."
            )
        }
        try validateOwner(existing, path: path)
        guard chmod(path, 0o600) == 0 else {
            throw posixFailure("Could not apply private Computer Use socket permissions")
        }
        let sealed = try fileStatus(at: path)
        guard SocketFileIdentity(sealed) == SocketFileIdentity(existing) else {
            throw SecureUnixDomainSocketError.alreadyInUse(
                "Computer Use socket changed while it was being sealed."
            )
        }
        try validatePrivatePermissions(sealed, path: path)
        boundIdentity = SocketFileIdentity(sealed)
    }

    public func removeOwnedSocket() throws {
        stateLock.lock()
        let descriptor = leaseDescriptor
        let ownedIdentity = boundIdentity
        leaseDescriptor = nil
        boundIdentity = nil
        defer {
            if let descriptor {
                _ = Darwin.close(descriptor)
            }
            stateLock.unlock()
        }
        guard descriptor != nil || ownedIdentity != nil else { return }
        guard let existing = try optionalFileStatus(at: path) else { return }
        guard let ownedIdentity,
              SocketFileIdentity(existing) == ownedIdentity
        else {
            return
        }
        guard fileType(existing) == S_IFSOCK else {
            throw SecureUnixDomainSocketError.unexpectedFileType(
                "Computer Use cleanup found its recorded inode with an unexpected type."
            )
        }
        try validateOwner(existing, path: path)
        guard unlink(path) == 0 else {
            throw posixFailure("Could not remove the Computer Use socket")
        }
    }

    func stageReplacementForServerShutdown() throws {
        stateLock.lock()
        defer { stateLock.unlock() }
        guard stagedReplacementPath == nil,
              let boundIdentity,
              let current = try optionalFileStatus(at: path),
              SocketFileIdentity(current) != boundIdentity
        else {
            return
        }
        let stagedPath = path + ".preserved-" + UUID().uuidString.lowercased()
        guard renamex_np(path, stagedPath, UInt32(RENAME_EXCL)) == 0 else {
            throw posixFailure(
                "Could not preserve a replacement Computer Use socket before shutdown"
            )
        }
        stagedReplacementPath = stagedPath
    }

    func restoreReplacementAfterServerShutdown() throws {
        stateLock.lock()
        defer { stateLock.unlock() }
        guard let stagedPath = stagedReplacementPath else { return }
        guard try optionalFileStatus(at: path) == nil else {
            throw SecureUnixDomainSocketError.alreadyInUse(
                "Computer Use socket path was occupied while restoring a preserved replacement."
            )
        }
        guard renamex_np(stagedPath, path, UInt32(RENAME_EXCL)) == 0 else {
            throw posixFailure(
                "Could not restore the preserved replacement Computer Use socket"
            )
        }
        stagedReplacementPath = nil
    }

    deinit {
        try? restoreReplacementAfterServerShutdown()
        try? removeOwnedSocket()
    }
}

public enum PrivateCapabilityFile {
    public static func read(path: String) throws -> Data {
        let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.hasPrefix("/"),
              URL(fileURLWithPath: trimmed).standardizedFileURL.path == trimmed
        else {
            throw SecureUnixDomainSocketError.invalidPath(
                "Computer Use capability file path must be absolute and standardized."
            )
        }
        let descriptor = trimmed.withCString { path in
            Darwin.open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW)
        }
        guard descriptor >= 0 else {
            if errno == ELOOP {
                throw SecureUnixDomainSocketError.unexpectedFileType(
                    "Computer Use capability must not be a symbolic link."
                )
            }
            throw posixFailure("Could not open the Computer Use capability file")
        }
        defer { _ = Darwin.close(descriptor) }

        var status = stat()
        guard Darwin.fstat(descriptor, &status) == 0 else {
            throw posixFailure("Could not inspect the open Computer Use capability file")
        }
        guard fileType(status) == S_IFREG else {
            throw SecureUnixDomainSocketError.unexpectedFileType(
                "Computer Use capability must be stored in a regular file."
            )
        }
        try validateOwner(status, path: trimmed)
        try validatePrivatePermissions(status, path: trimmed)
        guard status.st_size >= 32, status.st_size <= 4_096 else {
            throw SecureUnixDomainSocketError.invalidPath(
                "Computer Use capability file must contain between 32 and 4096 bytes."
            )
        }

        var data = Data(count: Int(status.st_size))
        try data.withUnsafeMutableBytes { bytes in
            var offset = 0
            while offset < bytes.count {
                let count = Darwin.read(
                    descriptor,
                    bytes.baseAddress?.advanced(by: offset),
                    bytes.count - offset
                )
                if count < 0, errno == EINTR { continue }
                guard count > 0 else {
                    if count == 0 {
                        throw SecureUnixDomainSocketError.systemCall(
                            "Computer Use capability file changed while it was being read."
                        )
                    }
                    throw posixFailure("Could not read the Computer Use capability file")
                }
                offset += count
            }
        }
        return data
    }
}

public actor ComputerUseBrokerUDSServer {
    public nonisolated let socket: SecureUnixDomainSocketPath

    private let server: GRPCServer<HTTP2ServerTransport.Posix>
    private var serveTask: Task<Void, Error>?

    public init(
        socket: SecureUnixDomainSocketPath,
        service: any RegistrableRPCService
    ) {
        self.socket = socket
        self.server = GRPCServer(
            transport: .http2NIOPosix(
                address: .unixDomainSocket(path: socket.path),
                transportSecurity: .plaintext
            ),
            services: [service]
        )
    }

    public func start() async throws {
        guard serveTask == nil else {
            throw SecureUnixDomainSocketError.systemCall(
                "Computer Use socket server is already running."
            )
        }
        try socket.prepareForBinding()
        let server = self.server
        let task = Task {
            try await server.serve()
        }
        serveTask = task
        do {
            _ = try await server.listeningAddress
            try socket.sealBoundSocket()
        } catch {
            try? socket.stageReplacementForServerShutdown()
            server.beginGracefulShutdown()
            _ = try? await task.value
            try? socket.restoreReplacementAfterServerShutdown()
            serveTask = nil
            try? socket.removeOwnedSocket()
            throw error
        }
    }

    public func wait() async throws {
        guard let serveTask else {
            throw SecureUnixDomainSocketError.systemCall(
                "Computer Use socket server has not started."
            )
        }
        defer {
            self.serveTask = nil
            try? socket.removeOwnedSocket()
        }
        try await serveTask.value
    }

    public func stop() async {
        guard let serveTask else {
            try? socket.removeOwnedSocket()
            return
        }
        do {
            try socket.stageReplacementForServerShutdown()
        } catch {
            return
        }
        server.beginGracefulShutdown()
        _ = try? await serveTask.value
        try? socket.restoreReplacementAfterServerShutdown()
        self.serveTask = nil
        try? socket.removeOwnedSocket()
    }
}

private func optionalFileStatus(at path: String) throws -> stat? {
    var status = stat()
    if lstat(path, &status) == 0 {
        return status
    }
    if errno == ENOENT {
        return nil
    }
    throw posixFailure("Could not inspect \(path)")
}

private func fileStatus(at path: String) throws -> stat {
    guard let status = try optionalFileStatus(at: path) else {
        throw SecureUnixDomainSocketError.invalidPath("Required path does not exist: \(path)")
    }
    return status
}

private func fileType(_ status: stat) -> mode_t {
    status.st_mode & mode_t(S_IFMT)
}

private struct SocketFileIdentity: Sendable, Equatable {
    let device: dev_t
    let inode: ino_t
    let generation: UInt32
    let birthSeconds: Int
    let birthNanoseconds: Int

    init(_ status: stat) {
        device = status.st_dev
        inode = status.st_ino
        generation = status.st_gen
        birthSeconds = status.st_birthtimespec.tv_sec
        birthNanoseconds = status.st_birthtimespec.tv_nsec
    }
}

private func acquireSocketLease(at lockPath: String) throws -> Int32 {
    let descriptor = lockPath.withCString { path in
        Darwin.open(
            path,
            O_CREAT | O_RDWR | O_CLOEXEC | O_NOFOLLOW | O_EXLOCK | O_NONBLOCK,
            mode_t(S_IRUSR | S_IWUSR)
        )
    }
    guard descriptor >= 0 else {
        let code = errno
        if code == EWOULDBLOCK || code == EAGAIN {
            throw SecureUnixDomainSocketError.alreadyInUse(
                "Another Computer Use broker owns the socket lifecycle lease."
            )
        }
        throw posixFailure("Could not acquire the Computer Use socket lifecycle lease", code: code)
    }
    do {
        var status = stat()
        guard fstat(descriptor, &status) == 0 else {
            throw posixFailure("Could not inspect the Computer Use socket lifecycle lease")
        }
        guard fileType(status) == S_IFREG else {
            throw SecureUnixDomainSocketError.unexpectedFileType(
                "Computer Use socket lifecycle lease must be a regular file."
            )
        }
        try validateOwner(status, path: lockPath)
        guard fchmod(descriptor, mode_t(S_IRUSR | S_IWUSR)) == 0 else {
            throw posixFailure("Could not secure the Computer Use socket lifecycle lease")
        }
        return descriptor
    } catch {
        _ = Darwin.close(descriptor)
        throw error
    }
}

private func unixDomainSocketIsLive(path: String) throws -> Bool {
    let descriptor = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
    guard descriptor >= 0 else {
        throw posixFailure("Could not create a Computer Use socket liveness probe")
    }
    defer { _ = Darwin.close(descriptor) }
    guard Darwin.fcntl(descriptor, F_SETFD, FD_CLOEXEC) == 0 else {
        throw posixFailure("Could not secure the Computer Use socket liveness probe")
    }
    let statusFlags = Darwin.fcntl(descriptor, F_GETFL)
    guard statusFlags >= 0,
          Darwin.fcntl(descriptor, F_SETFL, statusFlags | O_NONBLOCK) == 0
    else {
        throw posixFailure("Could not bound the Computer Use socket liveness probe")
    }

    var address = sockaddr_un()
    address.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
    address.sun_family = sa_family_t(AF_UNIX)
    let pathCapacity = MemoryLayout.size(ofValue: address.sun_path)
    path.withCString { source in
        withUnsafeMutablePointer(to: &address.sun_path) { destination in
            destination.withMemoryRebound(
                to: CChar.self,
                capacity: pathCapacity
            ) { bytes in
                _ = strlcpy(bytes, source, pathCapacity)
            }
        }
    }
    let result = withUnsafePointer(to: &address) { pointer in
        pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { socketAddress in
            Darwin.connect(
                descriptor,
                socketAddress,
                socklen_t(MemoryLayout<sockaddr_un>.size)
            )
        }
    }
    if result == 0 {
        return true
    }
    let code = errno
    if code == ECONNREFUSED || code == ENOENT {
        return false
    }
    if code == EINPROGRESS || code == EALREADY
        || code == EAGAIN || code == EWOULDBLOCK
    {
        return true
    }
    throw posixFailure("Could not prove that the Computer Use socket is stale", code: code)
}

private func validateOwner(_ status: stat, path: String) throws {
    guard status.st_uid == geteuid() else {
        throw SecureUnixDomainSocketError.invalidOwner(
            "Computer Use path is not owned by the current user: \(path)"
        )
    }
}

private func validatePrivatePermissions(_ status: stat, path: String) throws {
    guard status.st_mode & 0o077 == 0 else {
        throw SecureUnixDomainSocketError.unsafePermissions(
            "Computer Use path grants group or other access: \(path)"
        )
    }
}

private func posixFailure(
    _ operation: String,
    code: Int32 = errno
) -> SecureUnixDomainSocketError {
    SecureUnixDomainSocketError.systemCall("\(operation): \(String(cString: strerror(code)))")
}
