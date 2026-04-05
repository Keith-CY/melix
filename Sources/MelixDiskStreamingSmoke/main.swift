import Foundation
import MelixCLICore

@main
enum MelixDiskStreamingSmokeMain {
    static func main() async throws {
        let output = try await DiskStreamingSmokeCommand.renderReport(
            arguments: Array(CommandLine.arguments.dropFirst())
        )
        FileHandle.standardOutput.write(Data(output.utf8))
    }
}
