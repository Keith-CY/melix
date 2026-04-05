import Foundation
import MelixControlPlaneCore

public enum DiskStreamingSmokeCommand {
    public static func renderReport(
        arguments: [String],
        environment: [String: String] = ProcessInfo.processInfo.environment,
        clientBuilder: (@Sendable ([String: String]) -> any ControlPlaneXPCClient)? = nil,
        reportBuilder: (@Sendable (String, [String: String]) async throws -> DiskStreamingSmokeReport)? = nil
    ) async throws -> String {
        let options = try parseArguments(arguments)
        let report: DiskStreamingSmokeReport
        if let reportBuilder {
            report = try await reportBuilder(options.modelID, environment)
        } else {
            let client = clientBuilder?(environment) ?? MelixLocalRuntimeFactory.makeClient(environment: environment)
            report = try await DiskStreamingSmokeRunner(client: client).run(modelID: options.modelID)
        }
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(report)
        return String(decoding: data, as: UTF8.self) + "\n"
    }

    struct Options: Equatable {
        let modelID: String
    }

    static func parseArguments(_ arguments: [String]) throws -> Options {
        var modelID = "melix-dev-text"

        var index = 0
        while index < arguments.count {
            switch arguments[index] {
            case "--json":
                index += 1
            case "--model-id":
                let valueIndex = index + 1
                guard valueIndex < arguments.count else {
                    throw MelixCLIError.missingValue("--model-id")
                }
                modelID = arguments[valueIndex]
                index += 2
            default:
                throw MelixCLIError.usage(
                    """
                    Usage:
                      melix-disk-streaming-smoke [--model-id MODEL] [--json]
                    """
                )
            }
        }

        return Options(modelID: modelID)
    }
}
