import Foundation
import MelixControlPlaneCore

public enum SessionLifecycleSmokeCommand {
    public static func renderReport(
        arguments: [String],
        environment: [String: String] = ProcessInfo.processInfo.environment,
        clientBuilder: (@Sendable ([String: String]) -> any ControlPlaneXPCClient)? = nil,
        reportBuilder: (@Sendable (String, String, [String: String]) async throws -> SessionLifecycleSmokeReport)? = nil
    ) async throws -> String {
        let options = try parseArguments(arguments)
        let report: SessionLifecycleSmokeReport
        if let reportBuilder {
            report = try await reportBuilder(options.serverSessionID, options.modelID, environment)
        } else {
            let client = clientBuilder?(environment) ?? MelixLocalRuntimeFactory.makeClient(environment: environment)
            let runner = SessionLifecycleSmokeRunner(
                client: client,
                metricsPath: environment["MELIX_CONTROL_PLANE_METRICS_PATH"] ?? ""
            )
            report = try await runner.run(
                serverSessionID: options.serverSessionID,
                modelID: options.modelID
            )
        }
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(report)
        return String(decoding: data, as: UTF8.self) + "\n"
    }

    struct Options: Equatable {
        let serverSessionID: String
        let modelID: String
    }

    static func parseArguments(_ arguments: [String]) throws -> Options {
        var serverSessionID = ServerSessionRuntimeStore.defaultServerSessionID
        var modelID = "melix-dev-text"

        var index = 0
        while index < arguments.count {
            switch arguments[index] {
            case "--json":
                index += 1
            case "--server-session-id":
                let valueIndex = index + 1
                guard valueIndex < arguments.count else {
                    throw MelixCLIError.missingValue("--server-session-id")
                }
                serverSessionID = arguments[valueIndex]
                index += 2
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
                      melix-session-lifecycle-smoke [--server-session-id ID] [--model-id MODEL] [--json]
                    """
                )
            }
        }

        return Options(serverSessionID: serverSessionID, modelID: modelID)
    }
}
