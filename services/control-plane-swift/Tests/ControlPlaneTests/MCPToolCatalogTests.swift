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
