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
            if invocation?.outputFormat == .jsonV1 || MelixCLIParser.requestedOutputFormat(arguments) == .jsonV1 {
                let commandID = invocation.map { MelixCLICommandCodec.commandID(for: $0.command) } ?? "unknown"
                let traceID = invocation?.traceID.isEmpty == false ? invocation?.traceID ?? "" : UUID().uuidString
                let envelope = Self.errorEnvelope(commandID: commandID, traceID: traceID, error: error)
                FileHandle.standardOutput.write(Data(envelope.utf8))
                Foundation.exit(EXIT_FAILURE)
            }
            FileHandle.standardError.write(Data((Self.message(for: error) + "\n").utf8))
            Foundation.exit(EXIT_FAILURE)
        }
    }

    private static func errorEnvelope(commandID: String, traceID: String, error: Error) -> String {
        if let error = error as? MelixCLIError {
            return (try? MelixCLIJSONEnvelope.errorEnvelopeString(
                commandID: commandID,
                traceID: traceID,
                error: error
            )) ?? fallbackErrorEnvelope(commandID: commandID)
        }
        return (try? MelixCLIJSONEnvelope.errorEnvelopeString(
            commandID: commandID,
            traceID: traceID,
            code: "runtime",
            message: "\(error)"
        )) ?? fallbackErrorEnvelope(commandID: commandID)
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
