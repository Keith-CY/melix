import ComputerUseBrokerCore
import ComputerUseBrokerMacOS
import ComputerUseBrokerTransport
import Foundation

@main
struct ComputerUseBrokerCLI {
    static func main() async {
        let arguments = Array(CommandLine.arguments.dropFirst())
        if arguments == ["--version"] {
            print("melix-computer-broker 0.2.0")
            return
        }
        if arguments == ["--permissions"] {
            ProductionComputerUseBrokerFactory
                .prepareProcessForDesktopServices()
            await printPermissions()
            return
        }
        if arguments.count == 3, arguments[0] == "serve", arguments[1] == "--socket" {
            do {
                ProductionComputerUseBrokerFactory
                    .prepareProcessForDesktopServices()
                try await serve(socketPath: arguments[2])
            } catch {
                writeError("computer broker failed: \(error.localizedDescription)\n")
                Foundation.exit(1)
            }
            return
        }
        writeError(
            """
            usage: melix-computer-broker --permissions | --version | serve --socket <absolute-path>

            serve requires MELIX_COMPUTER_BROKER_CALLER_BUNDLE_ID,
            MELIX_COMPUTER_BROKER_CALLER_TEAM_ID, and
            MELIX_COMPUTER_BROKER_VERIFICATION_CAPABILITY_FILE, plus
            MELIX_COMPUTER_BROKER_AUTHORIZATION_PUBLIC_KEY_BASE64.

            """
        )
        Foundation.exit(2)
    }

    private static func printPermissions() async {
        let artifactRoot = resolvedArtifactRoot()
        let broker = ProductionComputerUseBrokerFactory.make(artifactRoot: artifactRoot)
        let snapshot = await broker.permissions()
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        do {
            let data = try encoder.encode(snapshot)
            FileHandle.standardOutput.write(data)
            FileHandle.standardOutput.write(Data("\n".utf8))
        } catch {
            writeError("permission encoding failed\n")
            Foundation.exit(1)
        }
    }

    private static func serve(socketPath: String) async throws {
        let environment = ProcessInfo.processInfo.environment
        let callerBundleID = try requiredEnvironment(
            "MELIX_COMPUTER_BROKER_CALLER_BUNDLE_ID",
            environment: environment
        )
        let callerTeamID = try requiredEnvironment(
            "MELIX_COMPUTER_BROKER_CALLER_TEAM_ID",
            environment: environment
        )
        let capabilityFile = try requiredEnvironment(
            "MELIX_COMPUTER_BROKER_VERIFICATION_CAPABILITY_FILE",
            environment: environment
        )
        let capability = try PrivateCapabilityFile.read(path: capabilityFile)
        let authorizationPublicKeyBase64 = try requiredEnvironment(
            "MELIX_COMPUTER_BROKER_AUTHORIZATION_PUBLIC_KEY_BASE64",
            environment: environment
        )
        guard let authorizationPublicKey = Data(
            base64Encoded: authorizationPublicKeyBase64
        ) else {
            throw CLIConfigurationError.invalidEnvironment(
                "MELIX_COMPUTER_BROKER_AUTHORIZATION_PUBLIC_KEY_BASE64"
            )
        }
        let artifactRoot = resolvedArtifactRoot()
        let handshake = try BrokerHandshakePolicy(
            protocolVersion: environment["MELIX_COMPUTER_BROKER_PROTOCOL_VERSION"] ?? "1",
            expectedCallerBundleID: callerBundleID,
            expectedCallerTeamID: callerTeamID,
            verificationCapability: capability
        )
        let configuration = try BrokerTransportConfiguration(
            handshake: handshake,
            toolAuthorizationVerifier: try BrokerToolAuthorizationVerifier(
                publicKeyRawRepresentation: authorizationPublicKey
            ),
            brokerVersion: "0.2.0",
            brokerInstanceID: environment["MELIX_SERVICE_INSTANCE_NAME"]
                ?? "computer-broker-\(UUID().uuidString.lowercased())",
            artifactRoot: artifactRoot
        )
        let broker = ProductionComputerUseBrokerFactory.make(artifactRoot: artifactRoot)
        let provider = ComputerUseBrokerGRPCProvider(
            broker: broker,
            configuration: configuration
        )
        let socket = try SecureUnixDomainSocketPath(path: socketPath)
        let server = ComputerUseBrokerUDSServer(socket: socket, service: provider)
        do {
            try await server.start()
            FileHandle.standardOutput.write(
                Data("melix-computer-broker listening on \(socket.path)\n".utf8)
            )
            try await server.wait()
        } catch {
            await server.stop()
            throw error
        }
    }

    private static func requiredEnvironment(
        _ name: String,
        environment: [String: String]
    ) throws -> String {
        guard let value = environment[name]?.trimmingCharacters(in: .whitespacesAndNewlines),
              !value.isEmpty
        else {
            throw CLIConfigurationError.missingEnvironment(name)
        }
        return value
    }

    private static func writeError(_ message: String) {
        FileHandle.standardError.write(Data(message.utf8))
    }

    private enum CLIConfigurationError: Error, LocalizedError {
        case missingEnvironment(String)
        case invalidEnvironment(String)

        var errorDescription: String? {
            switch self {
            case let .missingEnvironment(name):
                "Required environment variable is missing: \(name)"
            case let .invalidEnvironment(name):
                "Required environment variable is invalid: \(name)"
            }
        }
    }

    private static func resolvedArtifactRoot() -> URL {
        let environment = ProcessInfo.processInfo.environment
        if let runtimeDirectory = environment["MELIX_RUNTIME_DIR"]?
            .trimmingCharacters(in: .whitespacesAndNewlines),
           !runtimeDirectory.isEmpty
        {
            return URL(fileURLWithPath: runtimeDirectory, isDirectory: true)
                .appendingPathComponent("computer-use", isDirectory: true)
        }
        return FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-computer-use", isDirectory: true)
    }
}
