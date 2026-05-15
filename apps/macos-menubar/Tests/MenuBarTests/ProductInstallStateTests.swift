import Foundation
import Testing

@testable import AppMain

@Suite("Product Install State")
struct ProductInstallStateTests {
    @Test("filesystem provider reports update availability from the configured channel")
    func reportsUpdateAvailability() throws {
        let temporaryRoot = try makeTemporaryRoot(prefix: "melix-update-state")
        let manifestURL = temporaryRoot.appendingPathComponent("install-manifest.json")
        let updateChannelURL = temporaryRoot.appendingPathComponent("stable.json")
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        try writeUpdateChannel(latestVersion: "0.2.0", to: updateChannelURL)
        try writeManifest(
            to: manifestURL,
            productVersion: "0.1.0",
            updateChannelPath: updateChannelURL.path,
            logsDirectoryPath: temporaryRoot.path
        )

        let provider = FilesystemProductInstallStateProvider(
            manifestURL: manifestURL,
            updateChannelURL: updateChannelURL
        )
        let status = try #require(provider.updateStatus())

        #expect(status.isAvailable)
        #expect(status.checkSucceeded)
        #expect(status.summary == "Update available: 0.2.0")
    }

    @Test("filesystem provider resolves default manifest paths and normalizes versions from the environment")
    func resolvesDefaultPathsAndNormalizesVersions() throws {
        let temporaryRoot = try makeTemporaryRoot(prefix: "melix-default-manifest")
        let defaultManifestDirectory = temporaryRoot
            .appendingPathComponent(".melix/install", isDirectory: true)
        let manifestURL = defaultManifestDirectory.appendingPathComponent("install-manifest.json")
        let updateChannelURL = temporaryRoot.appendingPathComponent("stable.json")
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        try FileManager.default.createDirectory(at: defaultManifestDirectory, withIntermediateDirectories: true)
        try writeUpdateChannel(latestVersion: "1.0.0-beta.1", to: updateChannelURL)
        try writeManifest(
            to: manifestURL,
            productVersion: "v1.0.1+build.7",
            logsDirectoryPath: temporaryRoot.path
        )

        let provider = FilesystemProductInstallStateProvider(
            environment: [
                "HOME": temporaryRoot.path,
                "MELIX_UPDATE_CHANNEL_PATH": updateChannelURL.path,
            ]
        )
        let status = try #require(provider.updateStatus())

        #expect(status.checkSucceeded)
        #expect(status.isAvailable == false)
        #expect(status.summary == "Update: up to date")
        #expect(status.detail == "Current v1.0.1+build.7 on stable")
    }

    @Test("filesystem provider resolves default manifest from MELIX_HOME")
    func resolvesDefaultManifestFromMelixHome() throws {
        let temporaryRoot = try makeTemporaryRoot(prefix: "melix-default-manifest-home")
        let melixHome = temporaryRoot.appendingPathComponent("custom-melix-home", isDirectory: true)
        let manifestDirectory = melixHome.appendingPathComponent("install", isDirectory: true)
        let manifestURL = manifestDirectory.appendingPathComponent("install-manifest.json")
        let updateChannelURL = temporaryRoot.appendingPathComponent("stable.json")
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        try FileManager.default.createDirectory(at: manifestDirectory, withIntermediateDirectories: true)
        try writeUpdateChannel(latestVersion: "0.4.0", to: updateChannelURL)
        try writeManifest(
            to: manifestURL,
            productVersion: "0.3.0",
            logsDirectoryPath: temporaryRoot.path
        )

        let provider = FilesystemProductInstallStateProvider(
            environment: [
                "HOME": temporaryRoot.path,
                "MELIX_HOME": melixHome.path,
                "MELIX_UPDATE_CHANNEL_PATH": updateChannelURL.path,
            ]
        )
        let status = try #require(provider.updateStatus())

        #expect(status.checkSucceeded)
        #expect(status.isAvailable)
        #expect(status.summary == "Update available: 0.4.0")
    }

    @Test("filesystem provider honors explicit manifest environment overrides")
    func honorsExplicitManifestEnvironmentOverride() throws {
        let temporaryRoot = try makeTemporaryRoot(prefix: "melix-manifest-env")
        let manifestURL = temporaryRoot.appendingPathComponent("explicit-install-manifest.json")
        let updateChannelURL = temporaryRoot.appendingPathComponent("stable.json")
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        try writeUpdateChannel(latestVersion: "0.3.0", to: updateChannelURL)
        try writeManifest(
            to: manifestURL,
            productVersion: "0.2.0",
            updateChannelPath: updateChannelURL.path,
            logsDirectoryPath: temporaryRoot.path
        )

        let provider = FilesystemProductInstallStateProvider(
            environment: [
                "MELIX_PRODUCT_MANIFEST_PATH": manifestURL.path,
                "HOME": "",
            ]
        )
        let status = try #require(provider.updateStatus())

        #expect(status.checkSucceeded)
        #expect(status.isAvailable)
        #expect(status.summary == "Update available: 0.3.0")
    }

    @Test("filesystem provider reports unreadable update channels as failed checks")
    func reportsUnreadableUpdateChannels() throws {
        let temporaryRoot = try makeTemporaryRoot(prefix: "melix-missing-channel")
        let manifestURL = temporaryRoot.appendingPathComponent("install-manifest.json")
        let updateChannelURL = temporaryRoot.appendingPathComponent("missing.json")
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        try writeManifest(
            to: manifestURL,
            updateChannelPath: updateChannelURL.path,
            logsDirectoryPath: temporaryRoot.path
        )

        let provider = FilesystemProductInstallStateProvider(manifestURL: manifestURL)
        let status = try #require(provider.updateStatus())

        #expect(status.checkSucceeded == false)
        #expect(status.summary == "Update: check failed")
        #expect(status.detail.contains(updateChannelURL.path))
    }

    @Test("filesystem provider reports incomplete update channel metadata as failed checks")
    func reportsIncompleteUpdateChannelMetadata() throws {
        let temporaryRoot = try makeTemporaryRoot(prefix: "melix-incomplete-channel")
        let manifestURL = temporaryRoot.appendingPathComponent("install-manifest.json")
        let updateChannelURL = temporaryRoot.appendingPathComponent("stable.json")
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        try writeJSON([
            "channel": "stable",
            "latest_version": "",
        ], to: updateChannelURL)
        try writeManifest(
            to: manifestURL,
            updateChannelPath: updateChannelURL.path,
            logsDirectoryPath: temporaryRoot.path
        )

        let provider = FilesystemProductInstallStateProvider(manifestURL: manifestURL)
        let status = try #require(provider.updateStatus())

        #expect(status.checkSucceeded == false)
        #expect(status.summary == "Update: check failed")
        #expect(status.detail.contains("latest_version"))
    }

    @Test("filesystem provider classifies host port conflicts from control-plane logs")
    func classifiesHostPortConflicts() throws {
        let temporaryRoot = try makeTemporaryRoot(prefix: "melix-startup-state")
        let manifestURL = temporaryRoot.appendingPathComponent("install-manifest.json")
        let controlPlaneStderrURL = temporaryRoot.appendingPathComponent("control-plane.stderr.log")
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        try Data("bind() failed: Address already in use\n".utf8).write(to: controlPlaneStderrURL)
        try writeManifest(
            to: manifestURL,
            logsDirectoryPath: temporaryRoot.path,
            controlPlaneStderrPath: controlPlaneStderrURL.path
        )

        let provider = FilesystemProductInstallStateProvider(manifestURL: manifestURL)
        let diagnostic = try #require(provider.startupFailureDiagnostic(for: MenuBarTestError(description: "handshake failed")))

        #expect(diagnostic.classification == "host_port_conflict")
        #expect(diagnostic.userMessage.contains("12436"))
        #expect(diagnostic.userMessage.contains(controlPlaneStderrURL.path))
    }

    @Test("filesystem provider classifies control plane crashes from control-plane logs")
    func classifiesControlPlaneCrashes() throws {
        let temporaryRoot = try makeTemporaryRoot(prefix: "melix-control-plane-crash")
        let manifestURL = temporaryRoot.appendingPathComponent("install-manifest.json")
        let controlPlaneStdoutURL = temporaryRoot.appendingPathComponent("control-plane.stdout.log")
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        try Data("fatal error: bootstrap crashed\n".utf8).write(to: controlPlaneStdoutURL)
        try writeManifest(
            to: manifestURL,
            logsDirectoryPath: temporaryRoot.path,
            controlPlaneStdoutPath: controlPlaneStdoutURL.path
        )

        let provider = FilesystemProductInstallStateProvider(manifestURL: manifestURL)
        let diagnostic = try #require(provider.startupFailureDiagnostic(for: MenuBarTestError(description: "handshake failed")))

        #expect(diagnostic.classification == "control_plane_crash")
        #expect(diagnostic.userMessage.contains(temporaryRoot.path))
        #expect(diagnostic.detail == "fatal error: bootstrap crashed")
    }

    @Test("filesystem provider classifies worker crashes from worker logs")
    func classifiesWorkerCrashes() throws {
        let temporaryRoot = try makeTemporaryRoot(prefix: "melix-worker-crash")
        let manifestURL = temporaryRoot.appendingPathComponent("install-manifest.json")
        let missingPythonWorkerStderrURL = temporaryRoot.appendingPathComponent("python-worker.stderr.log")
        let swiftTextWorkerStderrURL = temporaryRoot.appendingPathComponent("swift-text-worker.stderr.log")
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        try Data("Traceback: worker crashed\n".utf8).write(to: swiftTextWorkerStderrURL)
        try writeManifest(
            to: manifestURL,
            logsDirectoryPath: temporaryRoot.path,
            pythonWorkerStderrPath: missingPythonWorkerStderrURL.path,
            swiftTextWorkerStderrPath: swiftTextWorkerStderrURL.path
        )

        let provider = FilesystemProductInstallStateProvider(manifestURL: manifestURL)
        let diagnostic = try #require(provider.startupFailureDiagnostic(for: MenuBarTestError(description: "handshake failed")))

        #expect(diagnostic.classification == "worker_crash")
        #expect(diagnostic.userMessage.contains(missingPythonWorkerStderrURL.path))
        #expect(diagnostic.detail == "Traceback: worker crashed")
    }

    @Test("filesystem provider falls back to startup hang diagnostics when logs are benign")
    func fallsBackToStartupHangDiagnostics() throws {
        let temporaryRoot = try makeTemporaryRoot(prefix: "melix-startup-hang")
        let manifestURL = temporaryRoot.appendingPathComponent("install-manifest.json")
        let pythonWorkerStdoutURL = temporaryRoot.appendingPathComponent("python-worker.stdout.log")
        let swiftTextWorkerStdoutURL = temporaryRoot.appendingPathComponent("swift-text-worker.stdout.log")
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        try Data("still booting\n".utf8).write(to: pythonWorkerStdoutURL)
        try Data("ready soon\n".utf8).write(to: swiftTextWorkerStdoutURL)
        try writeManifest(
            to: manifestURL,
            logsDirectoryPath: temporaryRoot.path,
            pythonWorkerStdoutPath: pythonWorkerStdoutURL.path,
            swiftTextWorkerStdoutPath: swiftTextWorkerStdoutURL.path
        )

        let provider = FilesystemProductInstallStateProvider(manifestURL: manifestURL)
        let diagnostic = try #require(provider.startupFailureDiagnostic(for: MenuBarTestError(description: "handshake failed")))

        #expect(diagnostic.classification == "startup_hang")
        #expect(diagnostic.userMessage.contains("http://127.0.0.1:12436/v1/models"))
        #expect(diagnostic.userMessage.contains(temporaryRoot.path))
        #expect(diagnostic.detail == "still booting")
    }

    @Test("filesystem provider returns nil without a resolvable manifest")
    func returnsNilWithoutResolvableManifest() {
        let provider = FilesystemProductInstallStateProvider(environment: ["HOME": ""])

        #expect(provider.updateStatus() == nil)
        #expect(provider.startupFailureDiagnostic(for: MenuBarTestError(description: "handshake failed")) == nil)
    }
}

private func makeTemporaryRoot(prefix: String) throws -> URL {
    let root = FileManager.default.temporaryDirectory
        .appendingPathComponent("\(prefix)-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    return root
}

private func writeUpdateChannel(latestVersion: String, to url: URL) throws {
    try writeJSON([
        "channel": "stable",
        "latest_version": latestVersion,
    ], to: url)
}

private func writeManifest(
    to url: URL,
    productVersion: String = "0.1.0",
    updateChannelPath: String? = nil,
    readyProbeURL: String = "http://127.0.0.1:12436/v1/models",
    httpPort: Int = 12436,
    logsDirectoryPath: String,
    controlPlaneStdoutPath: String? = nil,
    controlPlaneStderrPath: String? = nil,
    pythonWorkerStdoutPath: String? = nil,
    pythonWorkerStderrPath: String? = nil,
    swiftTextWorkerStdoutPath: String? = nil,
    swiftTextWorkerStderrPath: String? = nil
) throws {
    var payload: [String: Any] = [
        "product_version": productVersion,
        "ready_probe_url": readyProbeURL,
        "http_port": httpPort,
        "logs_dir": logsDirectoryPath,
    ]
    payload["update_channel_path"] = updateChannelPath
    payload["control_plane_stdout_path"] = controlPlaneStdoutPath
    payload["control_plane_stderr_path"] = controlPlaneStderrPath
    payload["python_worker_stdout_path"] = pythonWorkerStdoutPath
    payload["python_worker_stderr_path"] = pythonWorkerStderrPath
    payload["swift_text_worker_stdout_path"] = swiftTextWorkerStdoutPath
    payload["swift_text_worker_stderr_path"] = swiftTextWorkerStderrPath
    try writeJSON(payload, to: url)
}

private func writeJSON(_ payload: [String: Any?], to url: URL) throws {
    let compact = payload.compactMapValues { $0 }
    let data = try JSONSerialization.data(withJSONObject: compact, options: [.prettyPrinted, .sortedKeys])
    try data.write(to: url)
}
