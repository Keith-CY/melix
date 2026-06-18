import Foundation
import MelixControlPlaneCore

@main
enum MelixOpenAIConformanceHarnessMain {
    static func main() async {
        do {
            let cli = try OpenAIConformanceHarnessCLI.parse(
                arguments: Array(CommandLine.arguments.dropFirst())
            )
            let report = try await cli.run()
            print("OpenAI conformance report written to \(cli.outputURL.path)")
            print("passed=\(report.summary.passed) failed=\(report.summary.failed) skipped=\(report.summary.skipped)")
            if report.summary.failed > 0 {
                Foundation.exit(1)
            }
        } catch {
            fputs("\(error)\n", stderr)
            Foundation.exit(2)
        }
    }
}
