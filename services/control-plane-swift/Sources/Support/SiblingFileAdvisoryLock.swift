import Darwin
import Foundation

enum SiblingFileAdvisoryLock {
    static func withExclusiveLock<Result>(
        storeURL: URL,
        fileManager: FileManager,
        operation: () throws -> Result
    ) throws -> Result {
        try fileManager.createDirectory(
            at: storeURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )

        let lockURL = storeURL.appendingPathExtension("lock")
        let descriptor = try openExclusiveLockFile(at: lockURL)
        defer { _ = Darwin.close(descriptor) }

        return try operation()
    }

    private static func openExclusiveLockFile(at lockURL: URL) throws -> Int32 {
        while true {
            let descriptor = lockURL.withUnsafeFileSystemRepresentation { path -> Int32 in
                guard let path else {
                    return -1
                }
                // O_EXLOCK is a flock acquired atomically with open. It must
                // live on the sibling because atomic JSON writes replace the
                // data file's inode.
                return Darwin.open(
                    path,
                    O_CREAT | O_RDWR | O_CLOEXEC | O_EXLOCK,
                    mode_t(S_IRUSR | S_IWUSR)
                )
            }
            if descriptor >= 0 {
                return descriptor
            }
            let errorCode = errno
            guard errorCode == EINTR else {
                throw posixError(code: errorCode, path: lockURL.path)
            }
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
