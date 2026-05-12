import Foundation
import MelixCLICore

@main
struct MelixCLIExecutable {
    static func main() async {
        let arguments = Array(CommandLine.arguments.dropFirst())
        var invocation: MelixCLIInvocation?
        do {
            let parsedInvocation = try MelixCLIParser.parseInvocation(arguments)
            invocation = parsedInvocation
            let output = try await MelixCLIRunner().run(parsedInvocation)
            FileHandle.standardOutput.write(Data(output.utf8))
        } catch {
            let traceID = invocation?.traceID.isEmpty == false ? invocation?.traceID ?? "" : UUID().uuidString
            let commandID = invocation.map { MelixCLICommandCodec.commandID(for: $0.command) } ?? "unknown"
            let debugBundlePath = Self.writeEarlyFailureDebugBundle(
                commandID: commandID,
                traceID: traceID,
                arguments: arguments,
                error: error
            )
            if invocation?.outputFormat == .jsonV1 || MelixCLIParser.requestedOutputFormat(arguments) == .jsonV1 {
                let envelope = Self.errorEnvelope(
                    commandID: commandID,
                    traceID: traceID,
                    error: error,
                    debugBundlePath: debugBundlePath
                )
                FileHandle.standardOutput.write(Data(envelope.utf8))
                Foundation.exit(EXIT_FAILURE)
            }
            var message = Self.message(for: error)
            if let debugBundlePath {
                message += "\nDebug bundle: \(debugBundlePath)"
            }
            FileHandle.standardError.write(Data((message + "\n").utf8))
            Foundation.exit(EXIT_FAILURE)
        }
    }

    private static func errorEnvelope(
        commandID: String,
        traceID: String,
        error: Error,
        debugBundlePath: String?
    ) -> String {
        let artifacts = debugBundlePath.map {
            [
                [
                    "kind": "debug_bundle",
                    "path": MelixDiagnosticsRedaction.redactString($0),
                ],
            ]
        } ?? []
        if let error = error as? MelixCLIError {
            return (try? MelixCLIJSONEnvelope.errorEnvelopeString(
                commandID: commandID,
                traceID: traceID,
                error: error,
                artifacts: artifacts
            )) ?? fallbackErrorEnvelope(commandID: commandID)
        }
        return (try? MelixCLIJSONEnvelope.errorEnvelopeString(
            commandID: commandID,
            traceID: traceID,
            code: "runtime",
            message: "\(error)",
            artifacts: artifacts
        )) ?? fallbackErrorEnvelope(commandID: commandID)
    }

    private static func writeEarlyFailureDebugBundle(
        commandID: String,
        traceID: String,
        arguments: [String],
        error: Error
    ) -> String? {
        let environment = ProcessInfo.processInfo.environment
        let store = MelixDiagnosticsStore(
            melixHome: MelixHome(environment: environment),
            environment: environment
        )
        return try? store.writeEarlyFailureBundle(
            commandID: commandID,
            arguments: arguments,
            errorMessage: message(for: error),
            traceID: traceID
        ).path
    }

    private static func fallbackErrorEnvelope(commandID: String) -> String {
        "{\"schema_version\":\"melix.cli.error.v1\",\"command_id\":\"\(commandID)\",\"status\":\"failed\"}\n"
    }

    private static func message(for error: Error) -> String {
        if let error = error as? MelixCLIError {
            return error.errorDescription ?? MelixCLIParser.usageText
        }
        return "\(error)"
    }
}
