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
        } catch let error as MelixCLIError {
            if invocation?.outputFormat == .jsonV1 || MelixCLIParser.requestedOutputFormat(arguments) == .jsonV1 {
                let commandID = invocation.map { MelixCLICommandCodec.commandID(for: $0.command) } ?? "unknown"
                let traceID = invocation?.traceID.isEmpty == false ? invocation?.traceID ?? "" : UUID().uuidString
                let envelope = (try? MelixCLIJSONEnvelope.errorEnvelopeString(
                    commandID: commandID,
                    traceID: traceID,
                    error: error
                )) ?? "{\"schema_version\":\"melix.cli.error.v1\",\"command_id\":\"\(commandID)\",\"status\":\"failed\"}\n"
                FileHandle.standardOutput.write(Data(envelope.utf8))
                Foundation.exit(EXIT_FAILURE)
            }
            let message = error.errorDescription ?? MelixCLIParser.usageText
            FileHandle.standardError.write(Data((message + "\n").utf8))
            Foundation.exit(EXIT_FAILURE)
        } catch {
            if invocation?.outputFormat == .jsonV1 || MelixCLIParser.requestedOutputFormat(arguments) == .jsonV1 {
                let commandID = invocation.map { MelixCLICommandCodec.commandID(for: $0.command) } ?? "unknown"
                let traceID = invocation?.traceID.isEmpty == false ? invocation?.traceID ?? "" : UUID().uuidString
                let envelope = (try? MelixCLIJSONEnvelope.errorEnvelopeString(
                    commandID: commandID,
                    traceID: traceID,
                    code: "runtime",
                    message: "\(error)"
                )) ?? "{\"schema_version\":\"melix.cli.error.v1\",\"command_id\":\"\(commandID)\",\"status\":\"failed\"}\n"
                FileHandle.standardOutput.write(Data(envelope.utf8))
                Foundation.exit(EXIT_FAILURE)
            }
            FileHandle.standardError.write(Data(("\(error)\n").utf8))
            Foundation.exit(EXIT_FAILURE)
        }
    }
}
