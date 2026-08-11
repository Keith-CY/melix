import Foundation
import Testing

@testable import MelixCLICore
import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Local Runtime Factory")
struct LocalRuntimeFactoryTests {
    @Test("explicit control-plane socket always selects the daemon route")
    func explicitControlPlaneSocketSelectsDaemonRoute() {
        let valid = MelixLocalRuntimeFactory.resolvedClientRoute(
            environment: ["MELIX_CONTROL_PLANE_SOCKET_PATH": " /tmp/control.sock "],
            processIsAlive: { _ in false },
            socketPathIsUsable: { _ in false }
        )
        let invalid = MelixLocalRuntimeFactory.resolvedClientRoute(
            environment: ["MELIX_CONTROL_PLANE_SOCKET_PATH": ""],
            processIsAlive: { _ in false },
            socketPathIsUsable: { _ in false }
        )

        #expect(valid == .controlPlaneIPC(socketPath: "/tmp/control.sock"))
        #expect(invalid == .controlPlaneIPC(socketPath: ""))
    }

    @Test("live descriptor selects its single control-plane daemon")
    func liveDescriptorSelectsControlPlaneDaemon() throws {
        let fixture = try ActiveRuntimeDescriptorFixture()
        defer { fixture.remove() }
        try fixture.write(fixture.descriptorJSON())

        let live = MelixLocalRuntimeFactory.resolvedClientRoute(
            environment: ["MELIX_ACTIVE_RUNTIME_PATH": fixture.descriptorURL.path],
            processIsAlive: { $0 == fixture.controlPlaneProcessID },
            socketPathIsUsable: { $0 == fixture.controlPlaneSocketPath }
        )
        let stale = MelixLocalRuntimeFactory.resolvedClientRoute(
            environment: ["MELIX_ACTIVE_RUNTIME_PATH": fixture.descriptorURL.path],
            processIsAlive: { _ in false },
            socketPathIsUsable: { _ in true }
        )

        #expect(live == .controlPlaneIPC(socketPath: fixture.controlPlaneSocketPath))
        #expect(stale == .inProcess)
    }

    @Test("in-process fallback fails closed when MELIX_HOME already has a writer")
    func inProcessFallbackRequiresTheSingleWriterLease() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(
            "melix-cli-single-writer-\(UUID().uuidString)",
            isDirectory: true
        )
        defer { try? FileManager.default.removeItem(at: root) }
        try FileManager.default.createDirectory(
            at: root,
            withIntermediateDirectories: true
        )
        let descriptorURL = root.appendingPathComponent("active-runtime.json")
        try Data("not-json".utf8).write(to: descriptorURL, options: .atomic)
        let environment = [
            "MELIX_HOME": root.path,
            "MELIX_REPO_ROOT": "/tmp/melix-single-writer-test",
            "MELIX_ACTIVE_RUNTIME_PATH": descriptorURL.path,
        ]

        let first = MelixLocalRuntimeFactory.makeClient(environment: environment)
        _ = try await first.handshake()

        let second = MelixLocalRuntimeFactory.makeClient(environment: environment)
        await #expect(throws: ControlPlaneXPCClientError.requestFailed(
            code: "control_plane_home_already_owned",
            message: "Another Melix control plane already owns this MELIX_HOME."
        )) {
            try await second.handshake()
        }
    }

    @Test("in-process and unavailable services preserve the complete execution boundary")
    func localRuntimeServicesForwardEveryExecutionOperation() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(
            "melix-cli-execution-boundary-\(UUID().uuidString)",
            isDirectory: true
        )
        defer { try? FileManager.default.removeItem(at: root) }
        try FileManager.default.createDirectory(
            at: root,
            withIntermediateDirectories: true
        )
        let environment = [
            "MELIX_HOME": root.path,
            "MELIX_REPO_ROOT": "/tmp/melix-execution-boundary-test",
        ]

        let context = MelixLocalRuntimeFactory.makeContext(environment: environment)
        _ = try await context.service.handshake(Melix_Controlplane_V1_HandshakeRequest())
        let subscription = await context.service.subscribe(
            Melix_Controlplane_V1_SubscribeRequest()
        )
        await context.service.unsubscribe(subscription.subscriptionID)
        _ = try? await context.service.startChat(
            ControlPlaneChatRequest(modelID: "", messages: [])
        )
        _ = try? await context.service.startAgentRun(
            Melix_Controlplane_V1_StartAgentRun(),
            actorID: "local-runtime-boundary-test",
            remoteTarget: nil
        )
        _ = try? await context.service.execute(
            Melix_Controlplane_V1_ControlPlaneRequest()
        )

        let unavailable = MelixLocalRuntimeFactory.makeContext(environment: environment)
        await #expect(throws: ControlPlaneXPCClientError.self) {
            try await unavailable.service.handshake(
                Melix_Controlplane_V1_HandshakeRequest()
            )
        }
        let unavailableSubscription = await unavailable.service.subscribe(
            Melix_Controlplane_V1_SubscribeRequest()
        )
        await unavailable.service.unsubscribe(unavailableSubscription.subscriptionID)
        await #expect(throws: ControlPlaneXPCClientError.self) {
            try await unavailable.service.startChat(
                ControlPlaneChatRequest(modelID: "", messages: [])
            )
        }
        await #expect(throws: ControlPlaneXPCClientError.self) {
            try await unavailable.service.startAgentRun(
                Melix_Controlplane_V1_StartAgentRun(),
                actorID: "local-runtime-boundary-test",
                remoteTarget: nil
            )
        }
        await #expect(throws: ControlPlaneXPCClientError.self) {
            try await unavailable.service.execute(
                Melix_Controlplane_V1_ControlPlaneRequest()
            )
        }

        let unsafeRoot = root.appendingPathComponent("unsafe-home", isDirectory: true)
        let unsafeStateTarget = root.appendingPathComponent(
            "unsafe-state-target",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: unsafeRoot,
            withIntermediateDirectories: true
        )
        try FileManager.default.createDirectory(
            at: unsafeStateTarget,
            withIntermediateDirectories: true
        )
        try FileManager.default.createSymbolicLink(
            at: unsafeRoot.appendingPathComponent("state", isDirectory: true),
            withDestinationURL: unsafeStateTarget
        )
        let unsafeHome = MelixLocalRuntimeFactory.makeContext(
            environment: ["MELIX_HOME": unsafeRoot.path]
        )
        await #expect(throws: ControlPlaneXPCClientError.requestFailed(
            code: "control_plane_home_ownership_unavailable",
            message: "MELIX_HOME state directory must be a current-user directory."
        )) {
            try await unsafeHome.service.handshake(
                Melix_Controlplane_V1_HandshakeRequest()
            )
        }
    }

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

    @Test("one explicit socket keeps the live descriptor companion")
    func oneExplicitSocketKeepsLiveDescriptorCompanion() throws {
        let fixture = try ActiveRuntimeDescriptorFixture()
        defer { fixture.remove() }
        try fixture.write(fixture.descriptorJSON(swiftTextSocketPath: "relative-stale-swift.sock"))

        let paths = MelixLocalRuntimeFactory.resolvedWorkerSocketPaths(
            environment: [
                "MELIX_ACTIVE_RUNTIME_PATH": fixture.descriptorURL.path,
                "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": "/tmp/explicit-swift.sock",
            ],
            processIsAlive: { fixture.runtimeProcessIDs.contains($0) },
            socketPathIsUsable: { $0 == fixture.pythonSocketPath }
        )

        #expect(paths.pythonWorkerSocketPath == fixture.pythonSocketPath)
        #expect(paths.swiftTextWorkerSocketPath == "/tmp/explicit-swift.sock")

        try fixture.write(fixture.descriptorJSON(pythonSocketPath: "relative-stale-python.sock"))

        let explicitPythonPaths = MelixLocalRuntimeFactory.resolvedWorkerSocketPaths(
            environment: [
                "MELIX_ACTIVE_RUNTIME_PATH": fixture.descriptorURL.path,
                "MELIX_WORKER_SOCKET_PATH": "/tmp/explicit-python.sock",
            ],
            processIsAlive: { fixture.runtimeProcessIDs.contains($0) },
            socketPathIsUsable: { $0 == fixture.swiftTextSocketPath }
        )
        #expect(explicitPythonPaths.pythonWorkerSocketPath == "/tmp/explicit-python.sock")
        #expect(explicitPythonPaths.swiftTextWorkerSocketPath == fixture.swiftTextSocketPath)

        let blankExplicitPath = MelixLocalRuntimeFactory.resolvedWorkerSocketPaths(
            environment: [
                "MELIX_ACTIVE_RUNTIME_PATH": fixture.descriptorURL.path,
                "MELIX_WORKER_SOCKET_PATH": "",
            ],
            processIsAlive: { fixture.runtimeProcessIDs.contains($0) },
            socketPathIsUsable: { $0 == fixture.swiftTextSocketPath }
        )
        #expect(blankExplicitPath.pythonWorkerSocketPath.isEmpty)
        #expect(blankExplicitPath.swiftTextWorkerSocketPath == fixture.swiftTextSocketPath)
    }

    @Test("two explicit sockets atomically override the active runtime descriptor")
    func twoExplicitSocketsAtomicallyOverrideDescriptor() throws {
        let fixture = try ActiveRuntimeDescriptorFixture()
        defer { fixture.remove() }
        try fixture.write(fixture.descriptorJSON())

        let paths = MelixLocalRuntimeFactory.resolvedWorkerSocketPaths(
            environment: [
                "MELIX_ACTIVE_RUNTIME_PATH": fixture.descriptorURL.path,
                "MELIX_WORKER_SOCKET_PATH": "/tmp/explicit-python.sock",
                "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": "/tmp/explicit-swift.sock",
            ],
            processIsAlive: { _ in false },
            socketPathIsUsable: { _ in false }
        )

        #expect(paths.pythonWorkerSocketPath == "/tmp/explicit-python.sock")
        #expect(paths.swiftTextWorkerSocketPath == "/tmp/explicit-swift.sock")
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
    let controlPlaneSocketPath: String
    let appProcessID: Int32 = 41_001
    let controlPlaneProcessID: Int32 = 41_002
    let pythonWorkerProcessID: Int32 = 41_003
    let swiftTextWorkerProcessID: Int32 = 41_004

    var socketPaths: [String] {
        [pythonSocketPath, swiftTextSocketPath, controlPlaneSocketPath]
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
        controlPlaneSocketPath = rootURL.appendingPathComponent("control-plane.sock").path
        try FileManager.default.createDirectory(at: rootURL, withIntermediateDirectories: true)
    }

    func descriptorJSON(
        appProcessID overriddenAppProcessID: Int32? = nil,
        pythonSocketPath overriddenPythonSocketPath: String? = nil,
        swiftTextSocketPath overriddenSwiftTextSocketPath: String? = nil
    ) -> String {
        let descriptorAppProcessID = overriddenAppProcessID ?? appProcessID
        let descriptorPythonSocketPath = overriddenPythonSocketPath ?? pythonSocketPath
        let descriptorSwiftTextSocketPath = overriddenSwiftTextSocketPath ?? swiftTextSocketPath
        return """
        {
          "schema_version": "melix.active_runtime.v1",
          "app_process_id": \(descriptorAppProcessID),
          "control_plane_process_id": \(controlPlaneProcessID),
          "python_worker_process_id": \(pythonWorkerProcessID),
          "swift_text_worker_process_id": \(swiftTextWorkerProcessID),
          "python_worker_socket_path": "\(descriptorPythonSocketPath)",
          "swift_text_worker_socket_path": "\(descriptorSwiftTextSocketPath)",
          "control_plane_socket_path": "\(controlPlaneSocketPath)",
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
