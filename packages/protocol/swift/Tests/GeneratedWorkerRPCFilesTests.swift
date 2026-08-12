import Foundation
import XCTest

final class GeneratedWorkerRPCFilesTests: XCTestCase {
    func testWorkerServiceStubFilesExist() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let workerRoot = packageRoot.appendingPathComponent("worker/v1", isDirectory: true)
        let expectedFiles = [
            "runtime.grpc.swift",
            "inference.grpc.swift",
            "cache.grpc.swift",
            "maintenance.grpc.swift",
            "tool_runtime.grpc.swift",
        ]

        let missingFiles = expectedFiles.filter { fileName in
            let filePath = workerRoot.appendingPathComponent(fileName).path
            return !FileManager.default.fileExists(atPath: filePath)
        }

        XCTAssertTrue(
            missingFiles.isEmpty,
            "Missing generated Swift worker RPC stubs: \(missingFiles.joined(separator: ", "))"
        )
    }

    func testComputerBrokerServiceStubFileExists() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let filePath = packageRoot
            .appendingPathComponent("computer/v1/computer.grpc.swift")
            .path

        XCTAssertTrue(
            FileManager.default.fileExists(atPath: filePath),
            "Missing generated Swift Computer Use broker RPC stub."
        )
    }

    func testControlPlaneIPCServiceStubFileExists() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let filePath = packageRoot
            .appendingPathComponent(
                "controlplane/v1/control_plane.grpc.swift"
            )
            .path

        XCTAssertTrue(
            FileManager.default.fileExists(atPath: filePath),
            "Missing generated Swift control-plane IPC RPC stub."
        )
    }
}
