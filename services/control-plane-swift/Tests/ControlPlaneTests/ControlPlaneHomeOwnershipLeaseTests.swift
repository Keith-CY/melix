import Darwin
import Foundation
import Testing

@testable import MelixControlPlaneCore

@Suite("Control Plane MELIX_HOME ownership", .serialized)
struct ControlPlaneHomeOwnershipLeaseTests {
    @Test("ownership errors preserve their exact operator copy")
    func ownershipErrorsPreserveTheirExactOperatorCopy() {
        #expect(ControlPlaneHomeOwnershipError.unsafePath("unsafe").errorDescription == "unsafe")
        #expect(ControlPlaneHomeOwnershipError.alreadyOwned("owned").errorDescription == "owned")
        #expect(ControlPlaneHomeOwnershipError.systemCall("system").errorDescription == "system")
    }

    @Test("acquire repairs a pre-existing public state directory")
    func acquireRepairsAPreExistingPublicStateDirectory() throws {
        let root = ownershipTemporaryRoot("permissions")
        defer { try? FileManager.default.removeItem(at: root) }
        let state = root.appendingPathComponent("state", isDirectory: true)
        try FileManager.default.createDirectory(
            at: state,
            withIntermediateDirectories: true
        )
        try FileManager.default.setAttributes(
            [.posixPermissions: NSNumber(value: 0o755)],
            ofItemAtPath: state.path
        )

        let lease = try ControlPlaneHomeOwnershipLease.acquire(
            environment: ["MELIX_HOME": root.path],
            fencingToken: "permission-repair"
        )
        defer { lease.release() }

        let attributes = try FileManager.default.attributesOfItem(atPath: state.path)
        #expect((attributes[.posixPermissions] as? NSNumber)?.intValue == 0o700)
    }

    @Test("acquire rejects a symlinked state directory")
    func acquireRejectsASymlinkedStateDirectory() throws {
        let root = ownershipTemporaryRoot("state-symlink")
        let target = ownershipTemporaryRoot("state-target")
        defer {
            try? FileManager.default.removeItem(at: root)
            try? FileManager.default.removeItem(at: target)
        }
        try FileManager.default.createDirectory(
            at: root,
            withIntermediateDirectories: true
        )
        try FileManager.default.createDirectory(
            at: target,
            withIntermediateDirectories: true
        )
        try FileManager.default.createSymbolicLink(
            at: root.appendingPathComponent("state", isDirectory: true),
            withDestinationURL: target
        )

        #expect(throws: ControlPlaneHomeOwnershipError.self) {
            _ = try ControlPlaneHomeOwnershipLease.acquire(
                environment: ["MELIX_HOME": root.path]
            )
        }
    }

    @Test("acquire closes a non-regular writer lease after inspection")
    func acquireClosesANonRegularWriterLeaseAfterInspection() throws {
        let root = ownershipTemporaryRoot("fifo-lock")
        defer { try? FileManager.default.removeItem(at: root) }
        let state = root.appendingPathComponent("state", isDirectory: true)
        try FileManager.default.createDirectory(
            at: state,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: NSNumber(value: 0o700)]
        )
        let lock = state.appendingPathComponent(
            "control-plane-writer.lock",
            isDirectory: false
        )
        #expect(mkfifo(lock.path, mode_t(S_IRUSR | S_IWUSR)) == 0)

        #expect(throws: ControlPlaneHomeOwnershipError.self) {
            _ = try ControlPlaneHomeOwnershipLease.acquire(
                environment: ["MELIX_HOME": root.path]
            )
        }
    }

    @Test("one writer owns a persisted fencing generation until release")
    func oneWriterOwnsTheFencingGeneration() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(
            "melix-home-owner-\(UUID().uuidString)",
            isDirectory: true
        )
        defer { try? FileManager.default.removeItem(at: root) }
        let environment = ["MELIX_HOME": root.path]

        let first = try ControlPlaneHomeOwnershipLease.acquire(
            environment: environment,
            fencingToken: "generation-one"
        )
        #expect(
            try String(contentsOfFile: first.lockPath, encoding: .utf8)
                == "generation-one\n"
        )
        do {
            let unexpected = try ControlPlaneHomeOwnershipLease.acquire(
                environment: environment,
                fencingToken: "generation-conflict"
            )
            unexpected.release()
            Issue.record("A second writer acquired the same MELIX_HOME.")
        } catch let error as ControlPlaneHomeOwnershipError {
            guard case .alreadyOwned = error else {
                Issue.record("Expected alreadyOwned, received \(error).")
                return
            }
        }

        first.release()
        let second = try ControlPlaneHomeOwnershipLease.acquire(
            environment: environment,
            fencingToken: "generation-two"
        )
        defer { second.release() }
        #expect(
            try String(contentsOfFile: second.lockPath, encoding: .utf8)
                == "generation-two\n"
        )
    }
}

private func ownershipTemporaryRoot(_ label: String) -> URL {
    FileManager.default.temporaryDirectory.appendingPathComponent(
        "melix-home-owner-\(label)-\(UUID().uuidString)",
        isDirectory: true
    )
}
