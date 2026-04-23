import Foundation

public enum AgentIntegrationExportTarget: String, CaseIterable, Identifiable, Sendable {
    case openAICompatible = "OpenAI-Compatible"
    case openClaw = "OpenClaw"
    case hermesAgent = "Hermes Agent"
    case openCode = "OpenCode"
    case codex = "Codex"

    public var id: String {
        rawValue
    }

    public var instructions: String {
        switch self {
        case .openAICompatible:
            return "Use Melix as a generic OpenAI-compatible endpoint for SDKs, HTTP clients, and smoke probes."
        case .openClaw:
            return "Register the selected Melix listener as an OpenAI-compatible provider inside the OpenClaw configuration."
        case .hermesAgent:
            return "Point Hermes Agent at the selected Melix listener and keep the API key placeholder reproducible."
        case .openCode:
            return "Bind OpenCode to the selected Melix runtime through its OpenAI-compatible provider settings."
        case .codex:
            return "Export OpenAI-compatible environment variables so Codex uses the selected Melix listener."
        }
    }

    public var configTitle: String {
        switch self {
        case .openAICompatible:
            return "JSON Fragment"
        case .openClaw:
            return "YAML Fragment"
        case .hermesAgent:
            return "TOML Fragment"
        case .openCode:
            return "JSON Fragment"
        case .codex:
            return "Environment Block"
        }
    }
}

public struct AgentIntegrationExport: Identifiable, Equatable, Sendable {
    public let target: AgentIntegrationExportTarget
    public let baseURL: String
    public let modelID: String
    public let authPlaceholder: String
    public let configFragment: String
    public let shellSnippet: String
    public let instructions: String

    public var id: AgentIntegrationExportTarget {
        target
    }

    public static func exports(
        from session: DesktopServerSessionState
    ) -> [AgentIntegrationExport] {
        AgentIntegrationExportTarget.allCases.map { target in
            makeExport(target: target, session: session)
        }
    }

    private static func makeExport(
        target: AgentIntegrationExportTarget,
        session: DesktopServerSessionState
    ) -> AgentIntegrationExport {
        let baseURL = session.effectiveBaseURL
        let modelID = session.modelID
        let authPlaceholder = session.integrationAuthValue
        let shellSnippet = shellSnippet(
            for: target,
            baseURL: baseURL,
            modelID: modelID,
            authMode: session.authMode,
            authPlaceholder: authPlaceholder
        )
        let configFragment = configFragment(
            for: target,
            baseURL: baseURL,
            modelID: modelID,
            authPlaceholder: authPlaceholder
        )

        return AgentIntegrationExport(
            target: target,
            baseURL: baseURL,
            modelID: modelID,
            authPlaceholder: authPlaceholder,
            configFragment: configFragment,
            shellSnippet: shellSnippet,
            instructions: target.instructions
        )
    }

    private static func configFragment(
        for target: AgentIntegrationExportTarget,
        baseURL: String,
        modelID: String,
        authPlaceholder: String
    ) -> String {
        switch target {
        case .openAICompatible:
            return """
            {
              "provider": "melix",
              "base_url": "\(baseURL)",
              "api_key": "\(authPlaceholder)",
              "model": "\(modelID)"
            }
            """
        case .openClaw:
            return """
            provider: melix
            type: openai-compatible
            base_url: "\(baseURL)"
            api_key: "\(authPlaceholder)"
            default_model: "\(modelID)"
            """
        case .hermesAgent:
            return """
            [providers.melix]
            type = "openai-compatible"
            base_url = "\(baseURL)"
            api_key = "\(authPlaceholder)"
            model = "\(modelID)"
            """
        case .openCode:
            return """
            {
              "providers": {
                "melix": {
                  "type": "openai-compatible",
                  "baseUrl": "\(baseURL)",
                  "apiKey": "\(authPlaceholder)",
                  "defaultModel": "\(modelID)"
                }
              }
            }
            """
        case .codex:
            return """
            OPENAI_BASE_URL=\(baseURL)
            OPENAI_API_KEY=\(authPlaceholder)
            OPENAI_MODEL=\(modelID)
            """
        }
    }

    private static func shellSnippet(
        for target: AgentIntegrationExportTarget,
        baseURL: String,
        modelID: String,
        authMode: DesktopServerAuthMode,
        authPlaceholder: String
    ) -> String {
        let authorizationLine: String = switch authMode {
        case .none:
            ""
        case .bearerToken:
            """
              -H "Authorization: Bearer \(authPlaceholder)" \\
            """
        case .apiKeys:
            """
              -H "x-api-key: \(authPlaceholder)" \\
            """
        }

        switch target {
        case .openAICompatible:
            return """
            curl \(baseURL)/responses \\
            \(authorizationLine)  -H "Content-Type: application/json" \\
              -d '{"model":"\(modelID)","input":"Hello from Melix"}'
            """
        case .openClaw:
            return """
            OPENCLAW_BASE_URL="\(baseURL)" OPENCLAW_API_KEY="\(authPlaceholder)" \\
              openclaw chat --provider melix --model "\(modelID)"
            """
        case .hermesAgent:
            return """
            HERMES_AGENT_BASE_URL="\(baseURL)" HERMES_AGENT_API_KEY="\(authPlaceholder)" \\
              hermes-agent run --provider melix --model "\(modelID)" prompt.txt
            """
        case .openCode:
            return """
            OPENCODE_BASE_URL="\(baseURL)" OPENCODE_API_KEY="\(authPlaceholder)" \\
              opencode --provider melix --model "\(modelID)"
            """
        case .codex:
            return """
            OPENAI_BASE_URL="\(baseURL)" OPENAI_API_KEY=\(authPlaceholder) \\
              codex chat --model "\(modelID)"
            """
        }
    }
}
