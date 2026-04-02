import Foundation
import MelixCLICore

@main
struct MelixCLIExecutable {
    static func main() async {
        do {
            let command = try MelixCLIParser.parse(Array(CommandLine.arguments.dropFirst()))
            let output = try await MelixCLIRunner().run(command)
            FileHandle.standardOutput.write(Data(output.utf8))
        } catch let error as MelixCLIError {
            let message = error.errorDescription ?? MelixCLIParser.usageText
            FileHandle.standardError.write(Data((message + "\n").utf8))
            Foundation.exit(EXIT_FAILURE)
        } catch {
            FileHandle.standardError.write(Data(("\(error)\n").utf8))
            Foundation.exit(EXIT_FAILURE)
        }
    }
}
