import Foundation
import Testing

@testable import MelixCLICore

@Suite("Local Runtime Factory")
struct LocalRuntimeFactoryTests {
    @Test("active runtime descriptor supplies the paired worker sockets")
    func activeRuntimeDescriptorSuppliesPairedWorkerSockets() throws {
        let fixture = try ActiveRuntimeDescriptorFixture()
        defer { fixture.remove() }

        try fixture.write(fixture.descriptorJSON())

        let paths = MelixLocalRuntimeFactory.resolvedWorkerSocketPaths(
            environment: ["MELIX_ACTIVE_RUNTIME_PATH": fixture.descriptorURL.path],
            processIsAlive: { fixture.runtimeProcessIDs.contains($0) },
            socketPathIsUsable: { fixture.socketPaths.contains($0) }
        )

        #expect(paths.pythonWorkerSocketPath == fixture.pythonSocketPath)
        #expect(paths.swiftTextWorkerSocketPath == fixture.swiftTextSocketPath)
    }

    @Test("default Melix runtime directory supplies the active runtime descriptor")
    func defaultRuntimeDirectorySuppliesDescriptor() throws {
        let fixture = try ActiveRuntimeDescriptorFixture()
        defer { fixture.remove() }

        let melixHome = fixture.rootURL.appendingPathComponent("home", isDirectory: true)
        let descriptorURL = melixHome
            .appendingPathComponent("run", isDirectory: true)
            .appendingPathComponent("active-runtime.json", isDirectory: false)
        try FileManager.default.createDirectory(
            at: descriptorURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try fixture.write(fixture.descriptorJSON(), to: descriptorURL)

        let paths = MelixLocalRuntimeFactory.resolvedWorkerSocketPaths(
            environment: ["MELIX_HOME": melixHome.path],
            processIsAlive: { fixture.runtimeProcessIDs.contains($0) },
            socketPathIsUsable: fixture.socketPaths.contains
        )

        #expect(paths.pythonWorkerSocketPath == fixture.pythonSocketPath)
        #expect(paths.swiftTextWorkerSocketPath == fixture.swiftTextSocketPath)
    }

    @Test("production validators accept a live app and existing socket paths")
    func productionValidatorsAcceptLiveRuntime() throws {
        let fixture = try ActiveRuntimeDescriptorFixture()
        defer { fixture.remove() }
        try fixture.write(
            fixture.descriptorJSON(
                appProcessID: Int32(ProcessInfo.processInfo.processIdentifier)
            )
        )
        #expect(FileManager.default.createFile(atPath: fixture.pythonSocketPath, contents: Data()))
        #expect(FileManager.default.createFile(atPath: fixture.swiftTextSocketPath, contents: Data()))

        let paths = MelixLocalRuntimeFactory.resolvedWorkerSocketPaths(
            environment: ["MELIX_ACTIVE_RUNTIME_PATH": fixture.descriptorURL.path]
        )

        #expect(paths.pythonWorkerSocketPath == fixture.pythonSocketPath)
        #expect(paths.swiftTextWorkerSocketPath == fixture.swiftTextSocketPath)
    }

    @Test("explicit socket environment wins without mixing in descriptor values")
    func explicitSocketEnvironmentWinsAtomically() throws {
        let fixture = try ActiveRuntimeDescriptorFixture()
        defer { fixture.remove() }
        try fixture.descriptorJSON().write(to: fixture.descriptorURL, atomically: true, encoding: .utf8)

        let paths = MelixLocalRuntimeFactory.resolvedWorkerSocketPaths(
            environment: [
                "MELIX_ACTIVE_RUNTIME_PATH": fixture.descriptorURL.path,
                "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": "/tmp/explicit-swift.sock",
            ]
        )

        #expect(paths.pythonWorkerSocketPath == "/tmp/melix-worker.sock")
        #expect(paths.swiftTextWorkerSocketPath == "/tmp/explicit-swift.sock")

        let blankExplicitPath = MelixLocalRuntimeFactory.resolvedWorkerSocketPaths(
            environment: [
                "MELIX_ACTIVE_RUNTIME_PATH": fixture.descriptorURL.path,
                "MELIX_WORKER_SOCKET_PATH": "",
            ]
        )
        #expect(blankExplicitPath.pythonWorkerSocketPath.isEmpty)
        #expect(blankExplicitPath.swiftTextWorkerSocketPath == "/var/run/melix/swift-text-worker.sock")
    }

    @Test(
        "invalid active runtime descriptor falls back to existing defaults",
        arguments: [
            "not-json",
            """
            {"schema_version":"melix.active_runtime.v2","app_process_id":11,"control_plane_process_id":12,"python_worker_process_id":13,"swift_text_worker_process_id":14,"python_worker_socket_path":"/tmp/python.sock","swift_text_worker_socket_path":"/tmp/swift.sock","service_base_url":"http://127.0.0.1:12436/v1","updated_at_unix_ms":1000}
            """,
            """
            {"schema_version":"melix.active_runtime.v1","app_process_id":11,"control_plane_process_id":12,"python_worker_process_id":13,"swift_text_worker_process_id":14,"python_worker_socket_path":"relative-python.sock","swift_text_worker_socket_path":"/tmp/swift.sock","service_base_url":"http://127.0.0.1:12436/v1","updated_at_unix_ms":1000}
            """,
            """
            {"schema_version":"melix.active_runtime.v1","app_process_id":11,"control_plane_process_id":12,"python_worker_process_id":13,"swift_text_worker_process_id":14,"python_worker_socket_path":"/tmp/python.sock","service_base_url":"http://127.0.0.1:12436/v1","updated_at_unix_ms":1000}
            """,
        ]
    )
    func invalidDescriptorFallsBackToDefaults(contents: String) throws {
        let fixture = try ActiveRuntimeDescriptorFixture()
        defer { fixture.remove() }
        try fixture.write(contents)

        let paths = MelixLocalRuntimeFactory.resolvedWorkerSocketPaths(
            environment: ["MELIX_ACTIVE_RUNTIME_PATH": fixture.descriptorURL.path],
            processIsAlive: { _ in true },
            socketPathIsUsable: { _ in true }
        )

        #expect(paths.pythonWorkerSocketPath == "/tmp/melix-worker.sock")
        #expect(paths.swiftTextWorkerSocketPath == "/var/run/melix/swift-text-worker.sock")
    }

    @Test("dead app process or missing socket rejects an otherwise valid descriptor")
    func staleOrIncompleteRuntimeFallsBackToDefaults() throws {
        let fixture = try ActiveRuntimeDescriptorFixture()
        defer { fixture.remove() }
        try fixture.write(fixture.descriptorJSON())

        let stalePaths = MelixLocalRuntimeFactory.resolvedWorkerSocketPaths(
            environment: ["MELIX_ACTIVE_RUNTIME_PATH": fixture.descriptorURL.path],
            processIsAlive: { _ in false },
            socketPathIsUsable: { _ in true }
        )
        let incompletePaths = MelixLocalRuntimeFactory.resolvedWorkerSocketPaths(
            environment: ["MELIX_ACTIVE_RUNTIME_PATH": fixture.descriptorURL.path],
            processIsAlive: { _ in true },
            socketPathIsUsable: { $0 == fixture.pythonSocketPath }
        )
        let invalidLocations = [
            fixture.rootURL.appendingPathComponent("missing.json").path,
            "",
            "relative/active-runtime.json",
        ]

        #expect(stalePaths == .defaults)
        #expect(incompletePaths == .defaults)
        for location in invalidLocations {
            let paths = MelixLocalRuntimeFactory.resolvedWorkerSocketPaths(
                environment: ["MELIX_ACTIVE_RUNTIME_PATH": location],
                processIsAlive: { _ in true },
                socketPathIsUsable: { _ in true }
            )
            #expect(paths == .defaults)
        }
    }

    @Test("active runtime descriptor must remain private to the current user")
    func activeRuntimeDescriptorWithUnsafePermissionsFallsBackToDefaults() throws {
        let fixture = try ActiveRuntimeDescriptorFixture()
        defer { fixture.remove() }
        try fixture.write(fixture.descriptorJSON())
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o644],
            ofItemAtPath: fixture.descriptorURL.path
        )

        let paths = MelixLocalRuntimeFactory.resolvedWorkerSocketPaths(
            environment: ["MELIX_ACTIVE_RUNTIME_PATH": fixture.descriptorURL.path],
            processIsAlive: { _ in true },
            socketPathIsUsable: { _ in true }
        )

        #expect(paths == .defaults)
    }
}

private struct ActiveRuntimeDescriptorFixture {
    let rootURL: URL
    let descriptorURL: URL
    let pythonSocketPath: String
    let swiftTextSocketPath: String
    let appProcessID: Int32 = 41_001
    let controlPlaneProcessID: Int32 = 41_002
    let pythonWorkerProcessID: Int32 = 41_003
    let swiftTextWorkerProcessID: Int32 = 41_004

    var socketPaths: [String] {
        [pythonSocketPath, swiftTextSocketPath]
    }

    var runtimeProcessIDs: [Int32] {
        [appProcessID, controlPlaneProcessID, pythonWorkerProcessID, swiftTextWorkerProcessID]
    }

    init() throws {
        rootURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-active-runtime-\(UUID().uuidString)", isDirectory: true)
        descriptorURL = rootURL.appendingPathComponent("active-runtime.json", isDirectory: false)
        pythonSocketPath = rootURL.appendingPathComponent("python-worker.sock").path
        swiftTextSocketPath = rootURL.appendingPathComponent("swift-text-worker.sock").path
        try FileManager.default.createDirectory(at: rootURL, withIntermediateDirectories: true)
    }

    func descriptorJSON(appProcessID overriddenAppProcessID: Int32? = nil) -> String {
        let descriptorAppProcessID = overriddenAppProcessID ?? appProcessID
        return """
        {
          "schema_version": "melix.active_runtime.v1",
          "app_process_id": \(descriptorAppProcessID),
          "control_plane_process_id": \(controlPlaneProcessID),
          "python_worker_process_id": \(pythonWorkerProcessID),
          "swift_text_worker_process_id": \(swiftTextWorkerProcessID),
          "python_worker_socket_path": "\(pythonSocketPath)",
          "swift_text_worker_socket_path": "\(swiftTextSocketPath)",
          "service_base_url": "http://127.0.0.1:12436",
          "updated_at_unix_ms": 1784304000000
        }
        """
    }

    func write(_ contents: String) throws {
        try write(contents, to: descriptorURL)
    }

    func write(_ contents: String, to destinationURL: URL) throws {
        try contents.write(to: destinationURL, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o600],
            ofItemAtPath: destinationURL.path
        )
    }

    func remove() {
        try? FileManager.default.removeItem(at: rootURL)
    }
}
