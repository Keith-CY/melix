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
            report = try await reportBuilder(options.providerID, options.modelID, environment)
        } else {
            let client: any ControlPlaneXPCClient
            let flushMetrics: @Sendable () async -> Void
            if let clientBuilder {
                client = clientBuilder(environment)
                flushMetrics = {}
            } else {
                let context = MelixLocalRuntimeFactory.makeContext(environment: environment)
                client = LocalControlPlaneXPCClient(service: context.service)
                flushMetrics = {
                    await context.metricsStore.flushExport()
                }
            }
            let runner = SessionLifecycleSmokeRunner(
                client: client,
                metricsPath: environment["MELIX_CONTROL_PLANE_METRICS_PATH"] ?? "",
                flushMetrics: flushMetrics
            )
            report = try await runner.run(
                providerID: options.providerID,
                modelID: options.modelID
            )
        }
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(report)
        return String(decoding: data, as: UTF8.self) + "\n"
    }

    struct Options: Equatable {
        let providerID: String
        let modelID: String
    }

    static func parseArguments(_ arguments: [String]) throws -> Options {
        var providerID = MelixProviderDefaults.defaultProviderID
        var modelID = "melix-dev-text"

        var index = 0
        while index < arguments.count {
            switch arguments[index] {
            case "--json":
                index += 1
            case "--provider-id":
                let valueIndex = index + 1
                guard valueIndex < arguments.count else {
                    throw MelixCLIError.missingValue("--provider-id")
                }
                providerID = arguments[valueIndex]
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
                      melix-session-lifecycle-smoke [--provider-id ID] [--model-id MODEL] [--json]
                    """
                )
            }
        }

        return Options(providerID: providerID, modelID: modelID)
    }
}
