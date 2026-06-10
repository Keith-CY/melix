import Foundation
import Testing

@testable import AppMain

@Suite("Agent Integration Export Smoke", .serialized)
struct AgentIntegrationExportSmokeTests {
    @Test("agent integration export smoke fixture produces all targets")
    func agentIntegrationExportSmokeFixtureProducesAllTargets() throws {
        let session = DesktopProviderState(
            id: "provider-smoke",
            title: "Smoke Server",
            modelID: "melix-dev-text",
            host: "127.0.0.1",
            port: 8080,
            authMode: .bearerToken,
            authTokenHint: "smoke-token",
            lifecycle: .running
        )

        let exports = AgentIntegrationExport.exports(from: session)
        let exportByTarget = Dictionary(uniqueKeysWithValues: exports.map { ($0.target, $0) })

        #expect(exports.count == AgentIntegrationExportTarget.allCases.count)

        for target in AgentIntegrationExportTarget.allCases {
            let export = try #require(exportByTarget[target])
            #expect(export.baseURL == "http://127.0.0.1:8080/v1")
            #expect(export.modelID == "melix-dev-text")
            #expect(export.configFragment.contains("127.0.0.1:8080/v1"))
            #expect(export.configFragment.contains("<smoke-token>"))
            #expect(export.shellSnippet.contains("melix-dev-text"))
        }

        let openAICompatible = try #require(exportByTarget[.openAICompatible])
        #expect(openAICompatible.shellSnippet.contains("curl http://127.0.0.1:8080/v1/responses"))

        let codex = try #require(exportByTarget[.codex])
        #expect(codex.configFragment.contains("OPENAI_BASE_URL=http://127.0.0.1:8080/v1"))
        #expect(codex.configFragment.contains("OPENAI_API_KEY=<smoke-token>"))
    }

    @Test("agent integration export metric fixture records runtime metrics")
    @MainActor
    func agentIntegrationExportMetricFixtureRecordsRuntimeMetrics() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()

        let snapshot = await metrics.snapshot()
        let payload: [String: Double] = [
            "integration.export_generation_ms": snapshot["integration.export_generation_ms"] ?? -1,
            "integration.export_target_count": snapshot["integration.export_target_count"] ?? -1,
        ]
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
        let text = String(decoding: data, as: UTF8.self)
        print("M9_AGENT_EXPORT_METRICS=\(text)")

        #expect(payload["integration.export_generation_ms"] ?? -1 >= 0)
        #expect(payload["integration.export_target_count"] == Double(AgentIntegrationExportTarget.allCases.count))
        _ = viewModel
    }
}
