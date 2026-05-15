import Foundation
import Testing

@testable import MelixControlPlaneCore

struct MCPToolCatalogTests {
    @Test("environment loading returns empty catalog when config path is missing or blank")
    func environmentLoadingReturnsEmptyCatalogWhenConfigPathIsMissingOrBlank() {
        #expect(MCPToolCatalog.load(environment: [:]) == .empty)
        #expect(MCPToolCatalog.load(environment: ["MELIX_MCP_CONFIG_PATH": "   "]) == .empty)
    }

    @Test("config loading normalizes sources and parser mode")
    func configLoadingNormalizesSourcesAndParserMode() throws {
        let fixture = try makeFixture(
            """
            {
              "default_parser_mode": "mistral",
              "sources": [
                {
                  "source_id": " Filesystem ",
                  "enabled": true,
                  "namespaces": [" tools.fs.read ", "tools.fs.read", "tools.math", ""]
                },
                {
                  "source_id": "disabled-search",
                  "enabled": false,
                  "namespaces": ["tools.search"]
                },
                {
                  "source_id": " ",
                  "enabled": true,
                  "namespaces": ["tools.invalid"]
                },
                {
                  "source_id": "empty-tools",
                  "enabled": true,
                  "namespaces": [" ", ""]
                }
              ]
            }
            """
        )
        defer { try? FileManager.default.removeItem(at: fixture.deletingLastPathComponent()) }

        let catalog = MCPToolCatalog.load(environment: ["MELIX_MCP_CONFIG_PATH": " \(fixture.path) "])

        #expect(catalog.configPath == fixture.path)
        #expect(catalog.defaultParserMode == .mistral)
        #expect(catalog.sources.map(\.sourceID) == ["disabled-search", "filesystem"])
        #expect(catalog.sources[1].namespaces == ["tools.fs.read", "tools.math"])
        #expect(catalog.enabledSourceCount == 1)
        #expect(catalog.resolvedSourceIDs == ["filesystem"])
        #expect(catalog.resolvedNamespaces == ["tools.fs.read", "tools.math"])
        #expect(catalog.resolvedToolCount == 2)
        #expect(catalog.policyReceipt.effectivePolicy == "allow_configured")
        #expect(catalog.policyReceipt.refusedNamespaces.isEmpty)
    }

    @Test("config loading blocks high risk tool namespaces unless allowlisted")
    func configLoadingBlocksHighRiskToolNamespacesUnlessAllowlisted() throws {
        let fixture = try makeFixture(
            """
            {
              "default_parser_mode": "json",
              "sources": [
                {
                  "source_id": "filesystem",
                  "enabled": true,
                  "namespaces": ["tools.fs.read", "tools.fs.write", "tools.shell.exec"]
                },
                {
                  "source_id": "math",
                  "enabled": true,
                  "namespaces": ["tools.math"]
                },
                {
                  "source_id": "disabled-shell",
                  "enabled": false,
                  "namespaces": ["tools.terminal.exec"]
                }
              ]
            }
            """
        )
        defer { try? FileManager.default.removeItem(at: fixture.deletingLastPathComponent()) }

        let blocked = MCPToolCatalog.load(
            configPath: fixture.path,
            environment: [:]
        )
        let allowed = MCPToolCatalog.load(
            configPath: fixture.path,
            environment: ["MELIX_MCP_HIGH_RISK_ALLOWLIST": "tools.fs.write"]
        )
        let blockedSummary = blocked.summary()
        let allowedSummary = allowed.summary()

        #expect(blocked.resolvedNamespaces == ["tools.fs.read", "tools.math"])
        #expect(blocked.policyReceipt.requestedPolicy == "default_block_high_risk")
        #expect(blocked.policyReceipt.effectivePolicy == "block_high_risk")
        #expect(blocked.policyReceipt.refusedNamespaces == ["tools.fs.write", "tools.shell.exec"])
        #expect(blockedSummary.refusedNamespaces == ["tools.fs.write", "tools.shell.exec"])
        #expect(blockedSummary.effectivePolicy == "block_high_risk")

        #expect(allowed.resolvedNamespaces == ["tools.fs.read", "tools.fs.write", "tools.math"])
        #expect(allowed.policyReceipt.requestedPolicy == "operator_allowlist")
        #expect(allowed.policyReceipt.operatorOverrideSource == "MELIX_MCP_HIGH_RISK_ALLOWLIST")
        #expect(allowed.policyReceipt.refusedNamespaces == ["tools.shell.exec"])
        #expect(allowedSummary.refusedNamespaces == ["tools.shell.exec"])
        #expect(allowedSummary.operatorOverrideSource == "MELIX_MCP_HIGH_RISK_ALLOWLIST")
    }

    @Test("config loading falls back to an empty catalog for invalid files")
    func configLoadingFallsBackToAnEmptyCatalogForInvalidFiles() throws {
        let fixture = try makeFixture(
            """
            {
              "default_parser_mode": "json",
              "sources": "not-an-array"
            }
            """
        )
        defer { try? FileManager.default.removeItem(at: fixture.deletingLastPathComponent()) }

        let catalog = MCPToolCatalog.load(configPath: " \(fixture.path) ")

        #expect(catalog.configPath == fixture.path)
        #expect(catalog.defaultParserMode == .json)
        #expect(catalog.sources.isEmpty)
        #expect(catalog.enabledSources.isEmpty)
        #expect(catalog.resolvedNamespaces.isEmpty)
    }

    private func makeFixture(_ contents: String) throws -> URL {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
            UUID().uuidString,
            isDirectory: true
        )
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let file = directory.appendingPathComponent("mcp-tools.json")
        try Data(contents.utf8).write(to: file)
        return file
    }
}
