import Darwin
import Foundation
import Testing

@testable import MelixControlPlaneCore

@Suite("Sibling File Advisory Lock")
struct SiblingFileAdvisoryLockTests {
    @Test("a contended waiter yields to cancellation and the lock remains reusable")
    func contendedWaiterYieldsToCancellationAndLockRemainsReusable() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-sibling-lock-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let storeURL = temporaryRoot.appendingPathComponent("gateway-config.json")
        let lockURL = try SiblingFileAdvisoryLock.prepareLockURL(
            storeURL: storeURL,
            fileManager: .default
        )
        let owner = try await SiblingFileAdvisoryLock.acquire(lockURL: lockURL)

        let waiter = Task {
            try await SiblingFileAdvisoryLock.acquire(lockURL: lockURL)
        }
        try await Task.sleep(nanoseconds: 25_000_000)
        waiter.cancel()

        do {
            let unexpectedLease = try await waiter.value
            unexpectedLease.release()
            Issue.record("the contended waiter acquired a lock that was still owned")
        } catch is CancellationError {
            // Expected: the nonblocking retry loop observes cancellation.
        } catch {
            Issue.record("expected CancellationError, received \(error)")
        }

        owner.release()
        let nextOwner = try await SiblingFileAdvisoryLock.acquire(lockURL: lockURL)
        nextOwner.release()
    }

    @Test("cancellation after open closes the acquired descriptor")
    func cancellationAfterOpenClosesTheAcquiredDescriptor() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-sibling-lock-post-open-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let lockURL = temporaryRoot.appendingPathComponent("gateway-config.json.lock")
        let descriptor = lockURL.withUnsafeFileSystemRepresentation { path -> Int32 in
            guard let path else {
                return -1
            }
            return Darwin.open(
                path,
                O_CREAT | O_RDWR | O_CLOEXEC,
                mode_t(S_IRUSR | S_IWUSR)
            )
        }
        guard descriptor >= 0 else {
            Issue.record("failed to open the cancellation-race fixture descriptor")
            return
        }
        defer {
            if Darwin.fcntl(descriptor, F_GETFD) >= 0 {
                _ = Darwin.close(descriptor)
            }
        }

        let adoption = Task {
            while !Task.isCancelled {
                await Task.yield()
            }
            return try SiblingFileAdvisoryLock.validatedAcquiredDescriptor(descriptor)
        }
        adoption.cancel()

        do {
            _ = try await adoption.value
            Issue.record("a cancelled acquisition retained its descriptor")
        } catch is CancellationError {
            // Expected: the post-open guard closes before propagating cancellation.
        } catch {
            Issue.record("expected CancellationError, received \(error)")
        }

        errno = 0
        #expect(Darwin.fcntl(descriptor, F_GETFD) == -1)
        #expect(errno == EBADF)
    }
}
