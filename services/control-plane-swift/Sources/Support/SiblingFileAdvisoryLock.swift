import Darwin
import Foundation

enum SiblingFileAdvisoryLock {
    final class Lease: @unchecked Sendable {
        private let stateLock = NSLock()
        private var descriptor: Int32?

        fileprivate init(descriptor: Int32) {
            self.descriptor = descriptor
        }

        func release() {
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

    static func prepareLockURL(
        storeURL: URL,
        fileManager: FileManager
    ) throws -> URL {
        try fileManager.createDirectory(
            at: storeURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        return storeURL.appendingPathExtension("lock")
    }

    static func acquire(lockURL: URL) async throws -> Lease {
        return Lease(descriptor: try await openExclusiveLockFile(at: lockURL))
    }

    private static func openExclusiveLockFile(at lockURL: URL) async throws -> Int32 {
        while true {
            try Task.checkCancellation()
            let descriptor = lockURL.withUnsafeFileSystemRepresentation { path -> Int32 in
                guard let path else {
                    errno = EINVAL
                    return -1
                }
                // O_EXLOCK acquires the flock atomically with open. O_NONBLOCK
                // turns contention into EWOULDBLOCK so the cooperative Swift
                // executor can yield instead of parking one of its threads.
                return Darwin.open(
                    path,
                    O_CREAT | O_RDWR | O_CLOEXEC | O_EXLOCK | O_NONBLOCK,
                    mode_t(S_IRUSR | S_IWUSR)
                )
            }
            if descriptor >= 0 {
                return try validatedAcquiredDescriptor(descriptor)
            }
            let errorCode = errno
            if errorCode == EINTR {
                continue
            }
            if errorCode == EWOULDBLOCK || errorCode == EAGAIN {
                try await Task.sleep(nanoseconds: 5_000_000)
                continue
            }
            throw posixError(code: errorCode, path: lockURL.path)
        }
    }

    static func validatedAcquiredDescriptor(_ descriptor: Int32) throws -> Int32 {
        do {
            try Task.checkCancellation()
            return descriptor
        } catch {
            _ = Darwin.close(descriptor)
            throw error
        }
    }

    private static func posixError(code: Int32, path: String) -> NSError {
        NSError(
            domain: NSPOSIXErrorDomain,
            code: Int(code),
            userInfo: [NSFilePathErrorKey: path]
        )
    }
}
