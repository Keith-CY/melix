import Foundation
import MelixCLICore

@main
enum MelixSessionLifecycleSmokeMain {
    static func main() async throws {
        let output = try await SessionLifecycleSmokeCommand.renderReport(
            arguments: Array(CommandLine.arguments.dropFirst())
        )
        FileHandle.standardOutput.write(Data(output.utf8))
    }
}
