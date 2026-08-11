import Darwin
import Foundation
import Testing

@testable import MelixControlPlaneCore

struct MCPToolCatalogTests {
    @Test("environment loading returns empty catalog when config path is missing or blank")
    func environmentLoadingReturnsEmptyCatalogWhenConfigPathIsMissingOrBlank() {
        #expect(MCPToolCatalog.load(environment: [:]) == .empty)
        #expect(MCPToolCatalog.load(environment: ["MELIX_MCP_CONFIG_PATH": "   "]) == .empty)
    }

    @Test("explicit MCP config expands the current user's home directory")
    func explicitMCPConfigExpandsCurrentUserHomeDirectory() throws {
        let homeDirectory = FileManager.default.temporaryDirectory.appendingPathComponent(
            "melix-mcp-home-\(UUID().uuidString)",
            isDirectory: true
        )
        let configDirectory = homeDirectory.appendingPathComponent("agent-config", isDirectory: true)
        try FileManager.default.createDirectory(at: configDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: homeDirectory) }
        let configURL = configDirectory.appendingPathComponent("mcp-tools.json")
        try Data(
            """
            {"sources":[{"source_id":"home","namespaces":["tools.home"]}]}
            """.utf8
        ).write(to: configURL)

        let catalog = MCPToolCatalog.load(
            environment: [
                "HOME": homeDirectory.path,
                "MELIX_MCP_CONFIG_PATH": " ~/agent-config/mcp-tools.json ",
            ]
        )

        #expect(catalog.configurationState == .loaded)
        #expect(catalog.configPath == configURL.standardizedFileURL.path)
        #expect(catalog.discoverySource == .environment)
        #expect(catalog.resolvedSourceIDs == ["home"])

        let bareHome = MCPToolCatalog.load(
            configPath: "~",
            environment: ["HOME": homeDirectory.path]
        )
        #expect(bareHome.configurationState == .invalid)
        #expect(bareHome.configPath == homeDirectory.standardizedFileURL.path)

        let invalidConfiguredHomeSuffix = "melix-mcp-missing-\(UUID().uuidString).json"
        let invalidConfiguredHome = MCPToolCatalog.load(
            configPath: "~/\(invalidConfiguredHomeSuffix)",
            environment: ["HOME": "relative-home"]
        )
        #expect(invalidConfiguredHome.configurationState == .unreadable)
        #expect(
            invalidConfiguredHome.configPath
                == FileManager.default.homeDirectoryForCurrentUser
                    .appendingPathComponent(invalidConfiguredHomeSuffix)
                    .standardizedFileURL
                    .path
        )

        let redundantSeparatorDirectory = homeDirectory.appendingPathComponent(
            "tmp",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: redundantSeparatorDirectory,
            withIntermediateDirectories: true
        )
        let redundantSeparatorConfig = redundantSeparatorDirectory
            .appendingPathComponent("mcp-tools.json")
        try Data(
            """
            {"sources":[{"source_id":"redundant-separator","namespaces":["tools.home"]}]}
            """.utf8
        ).write(to: redundantSeparatorConfig)
        let redundantSeparatorCatalog = MCPToolCatalog.load(
            configPath: "~//tmp/mcp-tools.json",
            environment: ["HOME": homeDirectory.path]
        )
        #expect(redundantSeparatorCatalog.configurationState == .loaded)
        #expect(
            redundantSeparatorCatalog.configPath
                == redundantSeparatorConfig.standardizedFileURL.path
        )
    }

    @Test("explicit MCP config rejects cwd-relative and named-user paths")
    func explicitMCPConfigRejectsAmbiguousPaths() throws {
        let fixture = try makeFixture(
            """
            {"sources":[{"source_id":"cwd","namespaces":["tools.cwd"]}]}
            """
        )
        defer { try? FileManager.default.removeItem(at: fixture.deletingLastPathComponent()) }
        let existingRelativePath = relativePath(
            from: URL(
                fileURLWithPath: FileManager.default.currentDirectoryPath,
                isDirectory: true
            ),
            to: fixture
        )

        for configPath in [
            "mcp-tools.json",
            "./mcp-tools.json",
            "../mcp-tools.json",
            existingRelativePath,
            "~someone/mcp-tools.json",
            "/tmp/mcp\0-tools.json",
            "/" + String(repeating: "a", count: 4_097),
        ] {
            let catalog = MCPToolCatalog.load(
                environment: [
                    "HOME": "/tmp/melix-test-home",
                    "MELIX_MCP_CONFIG_PATH": configPath,
                ]
            )

            #expect(catalog.configurationState == .unreadable)
            #expect(catalog.configPath == configPath)
            #expect(catalog.discoverySource == .environment)
            #expect(catalog.resolvedSourceIDs.isEmpty)
        }

        let doubledAbsoluteRoot = MCPToolCatalog.load(
            configPath: "/" + fixture.path,
            environment: [:]
        )
        #expect(doubledAbsoluteRoot.configurationState == .loaded)
        #expect(doubledAbsoluteRoot.configPath == fixture.standardizedFileURL.path)
    }

    @Test("descriptor-first MCP read rejects a FIFO substituted after path resolution")
    func descriptorFirstMCPReadRejectsSubstitutedFIFO() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
            "melix-mcp-descriptor-read-\(UUID().uuidString)",
            isDirectory: true
        )
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let configURL = directory.appendingPathComponent("mcp-tools.json")
        let expectedData = Data(#"{"sources":[]}"#.utf8)
        try expectedData.write(to: configURL)
        let symlinkURL = directory.appendingPathComponent("mcp-tools-link.json")
        try FileManager.default.createSymbolicLink(
            at: symlinkURL,
            withDestinationURL: configURL
        )
        #expect(
            try MCPToolCatalog.boundedConfigurationData(atPath: symlinkURL.path)
                == expectedData
        )
        var didSubstituteFIFO = false

        #expect(throws: Error.self) {
            _ = try MCPToolCatalog.boundedConfigurationData(
                atPath: configURL.path,
                beforeOpeningResolvedURL: { resolvedURL in
                    try FileManager.default.removeItem(at: resolvedURL)
                    guard Darwin.mkfifo(resolvedURL.path, S_IRUSR | S_IWUSR) == 0 else {
                        throw CocoaError(.fileWriteUnknown)
                    }
                    didSubstituteFIFO = true
                }
            )
        }
        #expect(didSubstituteFIFO)
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
        let summary = catalog.summary()

        #expect(catalog.configPath == fixture.path)
        #expect(catalog.discoverySource == .environment)
        #expect(catalog.defaultParserMode == .mistral)
        #expect(catalog.sources.map(\.sourceID) == ["disabled-search", "filesystem"])
        #expect(catalog.sources[1].namespaces == ["tools.fs.read", "tools.math"])
        #expect(catalog.enabledSourceCount == 1)
        #expect(catalog.resolvedSourceIDs == ["filesystem"])
        #expect(catalog.resolvedNamespaces == ["tools.fs.read", "tools.math"])
        #expect(catalog.resolvedToolCount == 2)
        #expect(catalog.policyReceipt.effectivePolicy == "allow_configured")
        #expect(catalog.policyReceipt.refusedNamespaces.isEmpty)
        #expect(summary.sources.first?.sourceID == "config-discovery")
        #expect(summary.sources.first?.enabled == true)
        #expect(summary.sources.first?.namespaces == ["environment"])
        #expect(summary.sources.first?.policyState == "loaded")
    }

    @Test("environment loading discovers only explicit and MELIX_HOME MCP configs")
    func environmentLoadingDiscoversOnlyExplicitAndMelixHomeMCPConfigs() throws {
        let tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-mcp-discovery-\(UUID().uuidString)", isDirectory: true)
        let ignoredDirectory = tempDirectory.appendingPathComponent("ignored-cwd", isDirectory: true)
        let melixHome = tempDirectory.appendingPathComponent("home", isDirectory: true)
        let melixConfigDirectory = melixHome.appendingPathComponent("config", isDirectory: true)
        try FileManager.default.createDirectory(at: ignoredDirectory, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: melixConfigDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDirectory) }
        try Data(
            """
            {"sources":[{"source_id":"cwd","namespaces":["tools.cwd"]}]}
            """.utf8
        ).write(to: ignoredDirectory.appendingPathComponent("mcp-tools.json"))

        let absent = MCPToolCatalog.load(environment: ["MELIX_HOME": melixHome.path])
        try Data(
            """
            {"sources":[{"source_id":"home","namespaces":["tools.home"]}]}
            """.utf8
        ).write(to: melixConfigDirectory.appendingPathComponent("mcp-tools.json"))
        let discovered = MCPToolCatalog.load(environment: ["MELIX_HOME": melixHome.path])

        #expect(absent == .empty)
        #expect(discovered.discoverySource == .melixHome)
        #expect(discovered.resolvedSourceIDs == ["home"])
        #expect(discovered.resolvedNamespaces == ["tools.home"])
        #expect(discovered.summary().sources.first?.namespaces == ["melixHome"])
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
        #expect(blockedSummary.sources.first?.sourceID == "config-discovery")
        #expect(blockedSummary.sources.first?.namespaces == ["explicit"])

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
        #expect(catalog.configurationState == .invalid)
        #expect(catalog.configurationErrorCode == "config_invalid")
        #expect(catalog.summary().sources.first?.policyState == "config_invalid")

        let unreadable = MCPToolCatalog.load(
            configPath: fixture.deletingLastPathComponent()
                .appendingPathComponent("missing.json")
                .path
        )
        #expect(unreadable.configurationState == .unreadable)
        #expect(unreadable.configurationErrorCode == "config_unreadable")
    }

    @Test("standalone loading rejects non-regular and oversized MCP configs without unbounded reads")
    func standaloneLoadingRejectsNonRegularAndOversizedConfigs() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
            "melix-mcp-bounded-read-\(UUID().uuidString)",
            isDirectory: true
        )
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let oversizedURL = directory.appendingPathComponent("oversized.json")
        try Data(repeating: 0x20, count: 1_048_577).write(to: oversizedURL)
        let oversized = MCPToolCatalog.load(configPath: oversizedURL.path)
        #expect(oversized.configurationState == .invalid)
        #expect(oversized.configurationErrorCode == "config_invalid")

        let directoryCatalog = MCPToolCatalog.load(configPath: directory.path)
        #expect(directoryCatalog.configurationState == .invalid)

        if FileManager.default.fileExists(atPath: "/dev/zero") {
            let specialFile = MCPToolCatalog.load(configPath: "/dev/zero")
            #expect(specialFile.configurationState == .invalid)
            #expect(specialFile.sources.isEmpty)
        }
    }

    @Test("standalone loading enforces source and credential-reference cardinality")
    func standaloneLoadingEnforcesSourceAndReferenceCardinality() throws {
        let tooManySources = try makeFixture(
            object: [
                "sources": (0...256).map { index in
                    ["source_id": "source-\(index)", "namespaces": ["tools.read"]]
                },
            ]
        )
        defer { try? FileManager.default.removeItem(at: tooManySources.deletingLastPathComponent()) }
        #expect(MCPToolCatalog.load(configPath: tooManySources.path).configurationState == .invalid)

        let repeatedSourceReferences = Dictionary(
            uniqueKeysWithValues: (0...1_024).map { index in
                ("CHILD_\(index)", "MCP_SHARED_SECRET")
            }
        )
        let tooManyReferences = try makeFixture(
            object: [
                "sources": [[
                    "source_id": "stdio-source",
                    "transport": [
                        "kind": "stdio",
                        "command": "/usr/bin/env",
                        "environment_references": repeatedSourceReferences,
                    ],
                ]],
            ]
        )
        defer { try? FileManager.default.removeItem(at: tooManyReferences.deletingLastPathComponent()) }
        #expect(MCPToolCatalog.load(configPath: tooManyReferences.path).configurationState == .invalid)

        let oversizedTargetList = Dictionary(
            uniqueKeysWithValues: (0..<130).map { index in
                let prefix = "CHILD_\(index)_"
                let target = prefix + String(repeating: "A", count: 255 - prefix.utf8.count)
                return (target, "MCP_SHARED_SECRET")
            }
        )
        let targetBudgetExceeded = try makeFixture(
            object: [
                "sources": [[
                    "source_id": "target-budget",
                    "transport": [
                        "kind": "stdio",
                        "command": "/usr/bin/env",
                        "environment_references": oversizedTargetList,
                    ],
                ]],
            ]
        )
        defer { try? FileManager.default.removeItem(at: targetBudgetExceeded.deletingLastPathComponent()) }
        #expect(MCPToolCatalog.load(configPath: targetBudgetExceeded.path).configurationState == .invalid)

        let oversizedSourceKeyList = Dictionary(
            uniqueKeysWithValues: (0..<130).map { index in
                let prefix = "MCP_SECRET_\(index)_"
                let sourceKey = prefix + String(repeating: "A", count: 255 - prefix.utf8.count)
                return ("CHILD_\(index)", sourceKey)
            }
        )
        let sourceKeyBudgetExceeded = try makeFixture(
            object: [
                "sources": [[
                    "source_id": "source-key-budget",
                    "transport": [
                        "kind": "stdio",
                        "command": "/usr/bin/env",
                        "environment_references": oversizedSourceKeyList,
                    ],
                ]],
            ]
        )
        defer { try? FileManager.default.removeItem(at: sourceKeyBudgetExceeded.deletingLastPathComponent()) }
        #expect(MCPToolCatalog.load(configPath: sourceKeyBudgetExceeded.path).configurationState == .invalid)

        let staticHeaders = Dictionary(
            uniqueKeysWithValues: (0..<600).map { index in
                ("X-Static-\(index)", "melix")
            }
        )
        let referencedHeaders = Dictionary(
            uniqueKeysWithValues: (0..<600).map { index in
                ("X-Referenced-\(index)", "MCP_SHARED_SECRET")
            }
        )
        let combinedHeaderBudgetExceeded = try makeFixture(
            object: [
                "sources": [[
                    "source_id": "header-budget",
                    "transport": [
                        "kind": "streamable_http",
                        "url": "https://mcp.example.test/rpc",
                        "headers": staticHeaders,
                        "header_environment_references": referencedHeaders,
                    ],
                ]],
            ]
        )
        defer { try? FileManager.default.removeItem(at: combinedHeaderBudgetExceeded.deletingLastPathComponent()) }
        #expect(MCPToolCatalog.load(configPath: combinedHeaderBudgetExceeded.path).configurationState == .invalid)
    }

    @Test("standalone loading rejects invalid source and transport identifiers")
    func standaloneLoadingRejectsInvalidIdentifiers() throws {
        let invalidDocuments: [[String: Any]] = [
            [
                "sources": [[
                    "source_id": String(repeating: "a", count: 65),
                    "namespaces": ["tools.read"],
                ]],
            ],
            [
                "sources": [
                    ["source_id": "duplicate", "namespaces": ["tools.one"]],
                    ["source_id": "DUPLICATE", "namespaces": ["tools.two"]],
                ],
            ],
            [
                "sources": [[
                    "source_id": "stdio-source",
                    "transport": [
                        "kind": "stdio",
                        "command": "/usr/bin/env",
                        "environment_references": ["BAD-NAME": "MCP_SECRET"],
                    ],
                ]],
            ],
            [
                "sources": [[
                    "source_id": "stdio-source",
                    "transport": [
                        "kind": "stdio",
                        "command": "   ",
                    ],
                ]],
            ],
            [
                "sources": [[
                    "source_id": "stdio-source",
                    "transport": [
                        "kind": "stdio",
                        "command": "/usr/bin/env",
                        "working_directory": "relative/path",
                    ],
                ]],
            ],
            [
                "sources": [[
                    "source_id": "stdio-source",
                    "transport": [
                        "kind": "stdio",
                        "command": "/usr/bin/env",
                        "header_environment_references": ["Authorization": "MCP_SECRET"],
                    ],
                ]],
            ],
            [
                "sources": [[
                    "source_id": "http-source",
                    "transport": [
                        "kind": "streamable_http",
                        "url": "https://mcp.example.test/rpc",
                        "environment_references": ["TOKEN": "MCP_SECRET"],
                    ],
                ]],
            ],
            [
                "sources": [[
                    "source_id": "http-source",
                    "transport": [
                        "kind": "streamable_http",
                        "url": "http://mcp.example.test/rpc",
                    ],
                ]],
            ],
            [
                "sources": [[
                    "source_id": "http-source",
                    "transport": [
                        "kind": "streamable_http",
                        "url": "https://mcp.example.test/rpc",
                        "headers": ["Bad Header": "melix"],
                    ],
                ]],
            ],
            [
                "sources": [[
                    "source_id": "http-source",
                    "transport": [
                        "kind": "streamable_http",
                        "url": "https://mcp.example.test/rpc",
                        "header_environment_references": ["X-Token\r\nInjected": "MCP_SECRET"],
                    ],
                ]],
            ],
            [
                "sources": [[
                    "source_id": "http-source",
                    "transport": [
                        "kind": "streamable_http",
                        "url": "https://mcp.example.test/rpc",
                        "headers": ["X-Trace": "melix"],
                        "header_environment_references": ["x-trace": "MCP_SECRET"],
                    ],
                ]],
            ],
            [
                "sources": [[
                    "source_id": "http-source",
                    "transport": [
                        "kind": "streamable_http",
                        "url": "https://mcp.example.test/rpc",
                        "headers": ["Authorization": "Bearer literal-secret"],
                    ],
                ]],
            ],
        ]

        for document in invalidDocuments {
            let fixture = try makeFixture(object: document)
            defer { try? FileManager.default.removeItem(at: fixture.deletingLastPathComponent()) }
            let catalog = MCPToolCatalog.load(configPath: fixture.path)
            #expect(catalog.configurationState == .invalid)
            #expect(catalog.sources.isEmpty)
        }
    }

    @Test("raw config preflight rejects duplicate keys, explicit null, and non-standard constants")
    func rawConfigurationPreflightRejectsAmbiguousJSON() throws {
        let valid = Data(
            """
            {"sources":[{"source_id":"valid-source","namespaces":["tools.read"]}]}
            """.utf8
        )
        #expect(MCPToolCatalog.configurationDataPassesPreflight(valid))

        let invalidDocuments = [
            """
            {"sources":[],"sources":[]}
            """,
            """
            {"default_parser_mode":null,"sources":[]}
            """,
            """
            {"sources":[{"source_id":"null-enabled","enabled":null}]}
            """,
            """
            {"sources":[{"source_id":"null-transport","transport":null}]}
            """,
            """
            {"sources":[{"source_id":"null-arguments","transport":{"kind":"stdio","command":"/usr/bin/env","arguments":null}}]}
            """,
            """
            {"sources":[{"source_id":"null-headers","transport":{"kind":"streamable_http","url":"https://mcp.example.test/rpc","headers":null}}]}
            """,
            """
            {"unknown":NaN,"sources":[]}
            """,
            """
            {"unknown":1.0,"sources":[]}
            """,
            """
            {"sources":[{"source_id":"exponent-timeout","request_timeout_ms":1e0}]}
            """,
            """
            {"unknown":1e400,"sources":[]}
            """,
            #"{"sources":[{"source_id":"duplicate-escaped","transport":{"kind":"streamable_http","url":"https://mcp.example.test/rpc","headers":{"X-Trace":"one","\u0058-Trace":"two"}}}]}"#,
        ]

        for document in invalidDocuments {
            let data = Data(document.utf8)
            #expect(!MCPToolCatalog.configurationDataPassesPreflight(data))

            let fixture = try makeFixture(document)
            defer { try? FileManager.default.removeItem(at: fixture.deletingLastPathComponent()) }
            #expect(MCPToolCatalog.load(configPath: fixture.path).configurationState == .invalid)
        }
    }

    @Test("raw config preflight bounds nesting, value tokens, and object members")
    func rawConfigurationPreflightBoundsStructuralWork() {
        let maximumDepth = "{\"unknown\":"
            + String(repeating: "[", count: 126)
            + "0"
            + String(repeating: "]", count: 126)
            + ",\"sources\":[]}"
        #expect(MCPToolCatalog.configurationDataPassesPreflight(Data(maximumDepth.utf8)))

        let overMaximumDepth = "{\"unknown\":"
            + String(repeating: "[", count: 127)
            + "0"
            + String(repeating: "]", count: 127)
            + ",\"sources\":[]}"
        #expect(!MCPToolCatalog.configurationDataPassesPreflight(Data(overMaximumDepth.utf8)))

        let nearValueBudget = "{\"unknown\":["
            + Array(repeating: "0", count: 16_380).joined(separator: ",")
            + "],\"sources\":[]}"
        #expect(MCPToolCatalog.configurationDataPassesPreflight(Data(nearValueBudget.utf8)))

        let overValueBudget = "{\"unknown\":["
            + Array(repeating: "0", count: 16_384).joined(separator: ",")
            + "],\"sources\":[]}"
        #expect(!MCPToolCatalog.configurationDataPassesPreflight(Data(overValueBudget.utf8)))

        let overMemberBudget = "{"
            + (0..<8_192).map { "\"unknown_\($0)\":0" }.joined(separator: ",")
            + ",\"sources\":[]}"
        #expect(!MCPToolCatalog.configurationDataPassesPreflight(Data(overMemberBudget.utf8)))
    }

    @Test("live MCP transports survive config normalization and map to typed worker sources")
    func liveMCPTransportsMapToTypedWorkerSources() throws {
        let fixture = try makeFixture(
            """
            {
              "sources": [
                {
                  "source_id": " Local-Files ",
                  "transport": {
                    "kind": "stdio",
                    "command": "/usr/bin/env",
                    "arguments": ["python3", "server.py"],
                    "working_directory": "/tmp",
                    "environment_references": {
                      "TOKEN": "MELIX_TEST_MCP_TOKEN"
                    }
                  },
                  "request_timeout_ms": 9000,
                  "connect_timeout_ms": 12000,
                  "max_result_bytes": 8192,
                  "redaction_terms": ["private-value"],
                  "configuration_revision": "revision-7"
                },
                {
                  "source_id": "remote-search",
                  "enabled": false,
                  "transport": {
                    "kind": "streamable_http",
                    "url": "https://mcp.example.test/rpc",
                    "headers": {"X-Client": "melix"},
                    "header_environment_references": {
                      "Authorization": "MELIX_TEST_MCP_AUTH"
                    }
                  }
                }
              ]
            }
            """
        )
        defer { try? FileManager.default.removeItem(at: fixture.deletingLastPathComponent()) }

        let catalog = MCPToolCatalog.load(configPath: fixture.path, environment: [:])
        #expect(catalog.sources.map(\.sourceID) == ["local-files", "remote-search"])
        #expect(catalog.resolvedNamespaces.isEmpty)
        #expect(catalog.enabledSourceCount == 1)
        #expect(catalog.liveSourceConfigs.count == 2)

        let stdio = try #require(
            catalog.liveSourceConfigs.first(where: { $0.sourceID == "local-files" })
        )
        guard case .stdio(let transport)? = stdio.transport else {
            Issue.record("Expected stdio MCP transport")
            return
        }
        #expect(transport.command == "/usr/bin/env")
        #expect(transport.arguments == ["python3", "server.py"])
        #expect(transport.workingDirectory == "/tmp")
        #expect(transport.environmentReferences == ["TOKEN": "MELIX_TEST_MCP_TOKEN"])
        #expect(stdio.requestTimeoutMs == 9_000)
        #expect(stdio.connectTimeoutMs == 12_000)
        #expect(stdio.maxResultBytes == 8_192)
        #expect(stdio.redactionTerms == ["private-value"])
        #expect(stdio.configurationRevision == "revision-7")

        let remote = try #require(
            catalog.liveSourceConfigs.first(where: { $0.sourceID == "remote-search" })
        )
        guard case .streamableHTTP(let transport)? = remote.transport else {
            Issue.record("Expected Streamable HTTP MCP transport")
            return
        }
        #expect(remote.enabled == false)
        #expect(transport.url == "https://mcp.example.test/rpc")
        #expect(transport.headers == ["X-Client": "melix"])
        #expect(
            transport.headerEnvironmentReferences
                == ["Authorization": "MELIX_TEST_MCP_AUTH"]
        )
    }

    @Test("Streamable HTTP accepts bracketed IPv6 loopback")
    func streamableHTTPAcceptsBracketedIPv6Loopback() throws {
        let fixture = try makeFixture(
            """
            {
              "sources": [{
                "source_id": "loopback-ipv6",
                "transport": {
                  "kind": "streamable_http",
                  "url": "http://[::1]:12436/mcp"
                }
              }]
            }
            """
        )
        defer { try? FileManager.default.removeItem(at: fixture.deletingLastPathComponent()) }

        let catalog = MCPToolCatalog.load(configPath: fixture.path)

        #expect(catalog.configurationState == .loaded)
        #expect(catalog.liveSourceConfigs.first?.sourceID == "loopback-ipv6")
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

    private func makeFixture(object: Any) throws -> URL {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
            UUID().uuidString,
            isDirectory: true
        )
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let file = directory.appendingPathComponent("mcp-tools.json")
        try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]).write(to: file)
        return file
    }

    private func relativePath(from baseDirectory: URL, to target: URL) -> String {
        let baseComponents = baseDirectory.standardizedFileURL.pathComponents
        let targetComponents = target.standardizedFileURL.pathComponents
        var commonCount = 0
        while commonCount < min(baseComponents.count, targetComponents.count),
              baseComponents[commonCount] == targetComponents[commonCount]
        {
            commonCount += 1
        }
        let parentComponents = Array(
            repeating: "..",
            count: baseComponents.count - commonCount
        )
        return (parentComponents + targetComponents.dropFirst(commonCount)).joined(separator: "/")
    }
}
