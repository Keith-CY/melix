import Foundation
import MelixCLICore
import MelixControlPlaneCore

public enum DesktopSurface: String, CaseIterable, Identifiable, Codable, Sendable {
    case chat = "Chat"
    case commandCenter = "Command Center"
    case image = "Image"
    case server = "Servers"
    case models = "Models"
    case workflows = "Workflows"
    case jobs = "Jobs"
    case diagnostics = "Diagnostics"
    case tools = "Tools"
    case api = "API"
    case settings = "Settings"

    public var id: String {
        rawValue
    }

    public var symbolName: String {
        switch self {
        case .chat:
            return "message"
        case .commandCenter:
            return "command.circle"
        case .image:
            return "photo.on.rectangle"
        case .server:
            return "network"
        case .models:
            return "square.stack.3d.up"
        case .workflows:
            return "point.3.connected.trianglepath.dotted"
        case .jobs:
            return "list.bullet.rectangle.portrait"
        case .diagnostics:
            return "stethoscope"
        case .tools:
            return "wrench.and.screwdriver"
        case .api:
            return "chevron.left.forwardslash.chevron.right"
        case .settings:
            return "slider.horizontal.3"
        }
    }

    public static var visibleNavigationCases: [DesktopSurface] {
        [.chat, .commandCenter, .server, .models, .workflows, .jobs, .diagnostics, .api, .image, .settings]
    }

    public var routeDomainID: String {
        switch self {
        case .chat:
            return "chat"
        case .commandCenter:
            return "command"
        case .server:
            return "servers"
        case .models:
            return "models"
        case .workflows:
            return "workflows"
        case .jobs:
            return "jobs"
        case .diagnostics:
            return "diagnostics"
        case .api:
            return "api"
        case .image:
            return "image"
        case .settings:
            return "settings"
        case .tools:
            return "tools"
        }
    }
}

public enum DesktopToolSection: String, CaseIterable, Identifiable, Codable, Sendable {
    case modelsLibrary = "Models Library"
    case downloads = "Downloads"
    case training = "Training"
    case workflowRecipes = "Workflow Recipes"
    case syntheticDatasets = "Synthetic Datasets"
    case batchRuns = "Batch Runs"
    case jobs = "Jobs"
    case diagnostics = "Diagnostics"
    case logs = "Logs"
    case settings = "Settings"

    public var id: String {
        rawValue
    }

    public var symbolName: String {
        switch self {
        case .modelsLibrary:
            return "square.stack.3d.up"
        case .downloads:
            return "arrow.down.circle"
        case .training:
            return "figure.strengthtraining.traditional"
        case .workflowRecipes:
            return "list.bullet.clipboard"
        case .syntheticDatasets:
            return "sparkles.rectangle.stack"
        case .batchRuns:
            return "rectangle.stack.badge.play"
        case .jobs:
            return "list.bullet.rectangle.portrait"
        case .diagnostics:
            return "stethoscope"
        case .logs:
            return "doc.text.magnifyingglass"
        case .settings:
            return "slider.horizontal.3"
        }
    }
}

public enum DesktopToolCategory: String, CaseIterable, Identifiable, Codable, Sendable {
    case models = "Models"
    case workflows = "Workflows"
    case jobs = "Jobs"
    case diagnostics = "Diagnostics"
    case system = "System"

    public var id: String { rawValue }

    public var sections: [DesktopToolSection] {
        switch self {
        case .models:
            return [.modelsLibrary, .downloads]
        case .workflows:
            return [.training, .workflowRecipes, .syntheticDatasets, .batchRuns]
        case .jobs:
            return [.jobs]
        case .diagnostics:
            return [.diagnostics, .logs]
        case .system:
            return [.settings]
        }
    }
}

public enum DesktopSurfaceDomain: String, CaseIterable, Identifiable, Sendable {
    case models = "Models"
    case workflows = "Workflows"
    case jobs = "Jobs"
    case diagnostics = "Diagnostics"
    case settings = "Settings"

    public var id: String { rawValue }

    public var surface: DesktopSurface {
        switch self {
        case .models:
            return .models
        case .workflows:
            return .workflows
        case .jobs:
            return .jobs
        case .diagnostics:
            return .diagnostics
        case .settings:
            return .settings
        }
    }

    public var sections: [DesktopToolSection] {
        switch self {
        case .models:
            return [.modelsLibrary, .downloads]
        case .workflows:
            return [.training, .workflowRecipes, .syntheticDatasets, .batchRuns]
        case .jobs:
            return [.jobs]
        case .diagnostics:
            return [.diagnostics, .logs]
        case .settings:
            return [.settings]
        }
    }
}

extension DesktopToolSection {
    public var domain: DesktopSurfaceDomain {
        switch self {
        case .modelsLibrary, .downloads:
            return .models
        case .training, .workflowRecipes, .syntheticDatasets, .batchRuns:
            return .workflows
        case .jobs:
            return .jobs
        case .diagnostics, .logs:
            return .diagnostics
        case .settings:
            return .settings
        }
    }

    public var domainTitle: String {
        switch self {
        case .modelsLibrary:
            return "Library"
        case .syntheticDatasets:
            return "Dataset Generation"
        default:
            return rawValue
        }
    }

    public var breadcrumbTitle: String {
        "\(domain.rawValue) / \(domainTitle)"
    }
}

extension DesktopSurface {
    public var domain: DesktopSurfaceDomain? {
        switch self {
        case .models:
            return .models
        case .workflows:
            return .workflows
        case .jobs:
            return .jobs
        case .diagnostics:
            return .diagnostics
        case .settings:
            return .settings
        case .chat, .commandCenter, .image, .server, .tools, .api:
            return nil
        }
    }

    public var isDomainSurface: Bool {
        domain != nil
    }
}

public enum DesktopPaneRole: String, CaseIterable, Identifiable, Sendable {
    case sidebar
    case inspector

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .sidebar:
            return "Sidebar"
        case .inspector:
            return "Inspector"
        }
    }

    public var symbolName: String {
        switch self {
        case .sidebar:
            return "sidebar.left"
        case .inspector:
            return "sidebar.right"
        }
    }

    public func accessibilityLabel(isVisible: Bool) -> String {
        "\(isVisible ? "Hide" : "Show") \(title)"
    }
}

public struct DesktopPaneVisibilityState: Identifiable, Codable, Equatable, Sendable {
    public var surface: DesktopSurface
    public var showsSidebar: Bool
    public var showsInspector: Bool

    public var id: DesktopSurface { surface }

    public init(
        surface: DesktopSurface,
        showsSidebar: Bool = true,
        showsInspector: Bool = false
    ) {
        self.surface = surface
        self.showsSidebar = showsSidebar
        self.showsInspector = showsInspector
    }

    enum CodingKeys: String, CodingKey {
        case surfaceID = "surface"
        case showsSidebar = "shows_sidebar"
        case showsInspector = "shows_inspector"
    }

    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(
            surface: DesktopSurface(paneVisibilityID: try container.decodeIfPresent(String.self, forKey: .surfaceID) ?? "chat"),
            showsSidebar: try container.decodeIfPresent(Bool.self, forKey: .showsSidebar) ?? true,
            showsInspector: try container.decodeIfPresent(Bool.self, forKey: .showsInspector) ?? false
        )
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(surface.paneVisibilityID, forKey: .surfaceID)
        try container.encode(showsSidebar, forKey: .showsSidebar)
        try container.encode(showsInspector, forKey: .showsInspector)
    }

    public static func defaultState(for surface: DesktopSurface) -> DesktopPaneVisibilityState {
        DesktopPaneVisibilityState(
            surface: surface,
            showsSidebar: true,
            showsInspector: surface == .chat
        )
    }

    public static var defaultStates: [DesktopPaneVisibilityState] {
        DesktopSurface.allCases.map(defaultState(for:))
    }

    public static func mergedWithDefaults(
        _ states: [DesktopPaneVisibilityState]
    ) -> [DesktopPaneVisibilityState] {
        var bySurface = Dictionary(uniqueKeysWithValues: defaultStates.map { ($0.surface, $0) })
        for state in states {
            bySurface[state.surface] = state
        }
        return DesktopSurface.allCases.map { surface in
            bySurface[surface] ?? defaultState(for: surface)
        }
    }
}

public struct DesktopRuntimeEndpointState: Equatable, Sendable {
    public let serverSessionID: String
    public let serverTitle: String
    public let modelID: String
    public let requestedBaseURL: String
    public let effectiveBaseURL: String
    public let sharedAccessSummaryText: String

    public static let fallback = DesktopRuntimeEndpointState(
        serverSessionID: "",
        serverTitle: "No Server",
        modelID: "",
        requestedBaseURL: "http://\(MelixGatewayDefaults.host):\(MelixGatewayDefaults.port)/v1",
        effectiveBaseURL: "http://\(MelixGatewayDefaults.host):\(MelixGatewayDefaults.port)/v1",
        sharedAccessSummaryText: "No server session selected."
    )
}

public enum DesktopInspectorModule: String, CaseIterable, Identifiable, Codable, Sendable {
    case chatRuntime
    case commandCenter
    case serverProfile
    case capabilityReceipt
    case modelAsset
    case workflowTemplate
    case jobLineage
    case diagnosticsEvidence
    case apiInboundAuth
    case apiConsole
    case imageArtifact
    case runtimeStorage

    public var id: String { rawValue }
}

public enum DesktopRouteActionTarget: Equatable, Codable, Sendable {
    case page(domain: DesktopSurface, pageID: String)
}

public struct DesktopRouteActionMetadata: Equatable, Codable, Sendable {
    public let title: String
    public let target: DesktopRouteActionTarget

    public init(title: String, target: DesktopRouteActionTarget) {
        self.title = title
        self.target = target
    }
}

public struct DesktopRoutePageMetadata: Identifiable, Equatable, Codable, Sendable {
    public let id: String
    public let label: String
    public let title: String
    public let subtitle: String
    public let primaryAction: DesktopRouteActionMetadata?
    public let secondaryActions: [DesktopRouteActionMetadata]
    public let inspectorModule: DesktopInspectorModule
    public let routeDomainID: String

    public var crumb: String { domainLabel }
    public var routePath: String { "/\(routeDomainID)/\(id)" }

    public let domainLabel: String

    public init(
        id: String,
        label: String,
        title: String,
        subtitle: String,
        inspectorModule: DesktopInspectorModule,
        routeDomainID: String,
        domainLabel: String,
        primaryAction: DesktopRouteActionMetadata? = nil,
        secondaryActions: [DesktopRouteActionMetadata] = []
    ) {
        self.id = id
        self.label = label
        self.title = title
        self.subtitle = subtitle
        self.primaryAction = primaryAction
        self.secondaryActions = secondaryActions
        self.inspectorModule = inspectorModule
        self.routeDomainID = routeDomainID
        self.domainLabel = domainLabel
    }
}

public struct DesktopRouteDomainMetadata: Identifiable, Equatable, Codable, Sendable {
    public let domain: DesktopSurface
    public let pages: [DesktopRoutePageMetadata]

    public var id: String { domain.routeDomainID }

    public init(domain: DesktopSurface, pages: [DesktopRoutePageMetadata]) {
        self.domain = domain
        self.pages = pages
    }
}

public struct DesktopRouteMetadata: Equatable, Codable, Sendable {
    public let domains: [DesktopRouteDomainMetadata]

    public init(domains: [DesktopRouteDomainMetadata]) {
        self.domains = domains
    }

    public func page(domain: DesktopSurface, pageID: String) -> DesktopRoutePageMetadata? {
        domains.first { $0.domain == domain }?.pages.first { $0.id == pageID }
    }

    public static let acceptedWindowIA = DesktopRouteMetadata(domains: [
        .init(
            domain: .chat,
            pages: [
                .page(
                    domain: .chat,
                    id: "session",
                    label: "Session",
                    title: "Chat",
                    subtitle: "Chat sessions must bind to an explicit local or remote server before sending.",
                    inspectorModule: .chatRuntime
                ),
                .page(
                    domain: .chat,
                    id: "inspector-collapsed",
                    label: "Inspector Collapsed",
                    title: "Chat",
                    subtitle: "Chat remains usable when the runtime Inspector is collapsed.",
                    inspectorModule: .chatRuntime
                ),
            ]
        ),
        .init(
            domain: .commandCenter,
            pages: [
                .page(
                    domain: .commandCenter,
                    id: "overview",
                    label: "Overview",
                    title: "Command Center",
                    subtitle: "Shows what needs attention now without replacing Diagnostics evidence.",
                    inspectorModule: .commandCenter,
                    primaryAction: .init(
                        title: "Review Eval Drift",
                        target: .page(domain: .diagnostics, pageID: "evaluation")
                    ),
                    secondaryActions: [
                        .init(title: "Jobs", target: .page(domain: .jobs, pageID: "queue")),
                    ]
                ),
                .page(
                    domain: .commandCenter,
                    id: "menu-bar",
                    label: "Menu Bar Command Center",
                    title: "Menu Bar Command Center",
                    subtitle: "Compact command center state for menu bar operator access.",
                    inspectorModule: .commandCenter
                ),
            ]
        ),
        .init(
            domain: .server,
            pages: [
                .page(
                    domain: .server,
                    id: "overview",
                    label: "Overview",
                    title: "Servers",
                    subtitle: "Manage local and remote server profiles, health, credentials, and capability receipts.",
                    inspectorModule: .serverProfile,
                    primaryAction: .init(title: "Create Local Server", target: .page(domain: .server, pageID: "create-local")),
                    secondaryActions: [
                        .init(title: "Add Remote Server", target: .page(domain: .server, pageID: "add-remote")),
                    ]
                ),
                .page(
                    domain: .server,
                    id: "local",
                    label: "Local Servers",
                    title: "Local Servers",
                    subtitle: "Start, stop, and inspect local runtime profiles.",
                    inspectorModule: .serverProfile,
                    primaryAction: .init(title: "Create Local Server", target: .page(domain: .server, pageID: "create-local"))
                ),
                .page(
                    domain: .server,
                    id: "remote",
                    label: "Remote Servers",
                    title: "Remote Servers",
                    subtitle: "Manage outbound provider targets and credential boundaries.",
                    inspectorModule: .serverProfile,
                    primaryAction: .init(title: "Add Remote Server", target: .page(domain: .server, pageID: "add-remote"))
                ),
                .page(
                    domain: .server,
                    id: "create-local",
                    label: "Create Local Server",
                    title: "Create Local Server",
                    subtitle: "Basic setup first, advanced runtime fields collapsed for first-run creation.",
                    inspectorModule: .serverProfile,
                    primaryAction: .init(title: "Create And Start", target: .page(domain: .server, pageID: "local"))
                ),
                .page(
                    domain: .server,
                    id: "add-remote",
                    label: "Add Remote Server",
                    title: "Add Remote Server",
                    subtitle: "Endpoint, authentication, capability test, and review for outbound provider setup.",
                    inspectorModule: .capabilityReceipt,
                    primaryAction: .init(title: "Save Remote Server", target: .page(domain: .server, pageID: "remote"))
                ),
                .page(
                    domain: .server,
                    id: "receipts",
                    label: "Capability Receipts",
                    title: "Capability Receipts",
                    subtitle: "Evidence for runtime capabilities, unsupported routes, and probe freshness.",
                    inspectorModule: .capabilityReceipt
                ),
            ]
        ),
        .init(
            domain: .models,
            pages: [
                .page(
                    domain: .models,
                    id: "library",
                    label: "Library",
                    title: "Models",
                    subtitle: "Manage model and adapter assets without treating them as running endpoints.",
                    inspectorModule: .modelAsset,
                    primaryAction: .init(title: "Validate", target: .page(domain: .models, pageID: "library"))
                ),
                .page(
                    domain: .models,
                    id: "downloads-imports",
                    label: "Downloads & Imports",
                    title: "Downloads & Imports",
                    subtitle: "Download, import, validate, and convert model assets.",
                    inspectorModule: .modelAsset,
                    primaryAction: .init(title: "Start Download", target: .page(domain: .models, pageID: "downloads-imports"))
                ),
            ]
        ),
        .init(
            domain: .workflows,
            pages: [
                .page(
                    domain: .workflows,
                    id: "training",
                    label: "Training",
                    title: "Training",
                    subtitle: "Configure repeatable training workflows that produce adapter assets and jobs.",
                    inspectorModule: .workflowTemplate,
                    primaryAction: .init(title: "Train LoRA", target: .page(domain: .jobs, pageID: "queue"))
                ),
                .page(
                    domain: .workflows,
                    id: "recipes",
                    label: "Workflow Recipes",
                    title: "Workflow Recipes",
                    subtitle: "Apply reusable operation templates that create workflow drafts or jobs.",
                    inspectorModule: .workflowTemplate
                ),
                .page(
                    domain: .workflows,
                    id: "dataset-generation",
                    label: "Dataset Generation",
                    title: "Dataset Generation",
                    subtitle: "Generate durable datasets through repeatable workflow templates.",
                    inspectorModule: .workflowTemplate,
                    primaryAction: .init(title: "Create Dataset", target: .page(domain: .jobs, pageID: "queue"))
                ),
                .page(
                    domain: .workflows,
                    id: "batch-runs",
                    label: "Batch Runs",
                    title: "Batch Runs",
                    subtitle: "Run batch operations that produce durable job outputs.",
                    inspectorModule: .workflowTemplate,
                    primaryAction: .init(title: "Start Batch", target: .page(domain: .jobs, pageID: "queue"))
                ),
            ]
        ),
        .init(
            domain: .jobs,
            pages: [
                .page(
                    domain: .jobs,
                    id: "overview",
                    label: "Overview",
                    title: "Jobs",
                    subtitle: "Durable operation state across models, workflows, diagnostics, image, servers, and API.",
                    inspectorModule: .jobLineage,
                    primaryAction: .init(title: "Refresh Jobs", target: .page(domain: .jobs, pageID: "overview"))
                ),
                .page(
                    domain: .jobs,
                    id: "queue",
                    label: "Queue",
                    title: "Queue",
                    subtitle: "Queued and running work with blockers, recovery paths, and evidence links.",
                    inspectorModule: .jobLineage,
                    primaryAction: .init(title: "Refresh Jobs", target: .page(domain: .jobs, pageID: "queue"))
                ),
                .page(
                    domain: .jobs,
                    id: "history",
                    label: "History",
                    title: "History",
                    subtitle: "Completed jobs and artifact lineage across owner domains.",
                    inspectorModule: .jobLineage
                ),
            ]
        ),
        .init(
            domain: .diagnostics,
            pages: [
                .page(
                    domain: .diagnostics,
                    id: "overview",
                    label: "Overview",
                    title: "Diagnostics",
                    subtitle: "Canonical evidence and debugging workspace for runtime behavior.",
                    inspectorModule: .diagnosticsEvidence
                ),
                .page(
                    domain: .diagnostics,
                    id: "benchmark",
                    label: "Benchmark",
                    title: "Benchmark",
                    subtitle: "Measure latency, throughput, memory, and runtime path evidence.",
                    inspectorModule: .diagnosticsEvidence,
                    primaryAction: .init(title: "Run Benchmark", target: .page(domain: .jobs, pageID: "queue"))
                ),
                .page(
                    domain: .diagnostics,
                    id: "matrix",
                    label: "Matrix",
                    title: "Matrix",
                    subtitle: "Compare runtime and model behavior across benchmark axes.",
                    inspectorModule: .diagnosticsEvidence,
                    primaryAction: .init(title: "Run Matrix", target: .page(domain: .jobs, pageID: "queue"))
                ),
                .page(
                    domain: .diagnostics,
                    id: "evaluation",
                    label: "Evaluation",
                    title: "Evaluation",
                    subtitle: "Review eval evidence, semantic metrics, and human review state.",
                    inspectorModule: .diagnosticsEvidence,
                    primaryAction: .init(title: "Review Eval Drift", target: .page(domain: .diagnostics, pageID: "evaluation"))
                ),
                .page(
                    domain: .diagnostics,
                    id: "logs",
                    label: "Logs",
                    title: "Logs",
                    subtitle: "Inspect logs and debug bundles as evidence artifacts.",
                    inspectorModule: .diagnosticsEvidence
                ),
            ]
        ),
        .init(
            domain: .api,
            pages: [
                .page(
                    domain: .api,
                    id: "overview",
                    label: "Overview",
                    title: "API",
                    subtitle: "Developer integration overview for Melix endpoints and inbound access.",
                    inspectorModule: .apiConsole
                ),
                .page(
                    domain: .api,
                    id: "inbound-auth",
                    label: "Inbound Auth",
                    title: "Inbound Auth",
                    subtitle: "Configure credentials for clients calling Melix; remote provider credentials live under Servers.",
                    inspectorModule: .apiInboundAuth
                ),
                .page(
                    domain: .api,
                    id: "playground",
                    label: "Playground",
                    title: "Playground",
                    subtitle: "Request, response, headers, auth, latency, and receipt console.",
                    inspectorModule: .apiConsole,
                    primaryAction: .init(title: "Send Request", target: .page(domain: .api, pageID: "playground"))
                ),
                .page(
                    domain: .api,
                    id: "endpoints",
                    label: "Endpoints",
                    title: "Endpoints",
                    subtitle: "Supported routes, compatibility, and endpoint receipts.",
                    inspectorModule: .apiConsole
                ),
            ]
        ),
        .init(
            domain: .image,
            pages: [
                .page(
                    domain: .image,
                    id: "generate",
                    label: "Generate",
                    title: "Image",
                    subtitle: "Generate image artifacts with runtime and lineage visibility.",
                    inspectorModule: .imageArtifact,
                    primaryAction: .init(title: "Generate Image", target: .page(domain: .jobs, pageID: "queue"))
                ),
                .page(
                    domain: .image,
                    id: "edit",
                    label: "Edit",
                    title: "Edit",
                    subtitle: "Edit image artifacts with source, mask, revision, and lineage context.",
                    inspectorModule: .imageArtifact,
                    primaryAction: .init(title: "Apply Edit", target: .page(domain: .jobs, pageID: "queue"))
                ),
            ]
        ),
        .init(
            domain: .settings,
            pages: [
                .page(
                    domain: .settings,
                    id: "runtime-storage",
                    label: "Runtime & Storage",
                    title: "Runtime & Storage",
                    subtitle: "Configure runtime discovery, model roots, storage, and operator preferences.",
                    inspectorModule: .runtimeStorage
                ),
                .page(
                    domain: .settings,
                    id: "reserved-ia",
                    label: "Reserved IA",
                    title: "Reserved IA",
                    subtitle: "Reserved settings areas for security, retention, developer mode, logs, updates, and shortcuts.",
                    inspectorModule: .runtimeStorage
                ),
            ]
        ),
    ])
}

private extension DesktopRoutePageMetadata {
    static func page(
        domain: DesktopSurface,
        id: String,
        label: String,
        title: String,
        subtitle: String,
        inspectorModule: DesktopInspectorModule,
        primaryAction: DesktopRouteActionMetadata? = nil,
        secondaryActions: [DesktopRouteActionMetadata] = []
    ) -> DesktopRoutePageMetadata {
        DesktopRoutePageMetadata(
            id: id,
            label: label,
            title: title,
            subtitle: subtitle,
            inspectorModule: inspectorModule,
            routeDomainID: domain.routeDomainID,
            domainLabel: domain.rawValue,
            primaryAction: primaryAction,
            secondaryActions: secondaryActions
        )
    }
}

public enum DesktopSelectedObjectKind: String, CaseIterable, Identifiable, Codable, Sendable {
    case server
    case model
    case adapter
    case job
    case artifact
    case receipt
    case diagnosticReport = "diagnostic-report"
    case apiToken = "api-token"

    public var id: String { rawValue }

    public init?(routePrefix: String) {
        switch routePrefix.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "server":
            self = .server
        case "model":
            self = .model
        case "adapter":
            self = .adapter
        case "job":
            self = .job
        case "artifact":
            self = .artifact
        case "receipt":
            self = .receipt
        case "diagnostic-report", "eval":
            self = .diagnosticReport
        case "api-token", "token":
            self = .apiToken
        default:
            return nil
        }
    }

    public var defaultRoute: DesktopRouteActionTarget {
        switch self {
        case .server:
            return .page(domain: .server, pageID: "overview")
        case .model, .adapter:
            return .page(domain: .models, pageID: "library")
        case .job:
            return .page(domain: .jobs, pageID: "queue")
        case .artifact:
            return .page(domain: .jobs, pageID: "history")
        case .receipt:
            return .page(domain: .server, pageID: "receipts")
        case .diagnosticReport:
            return .page(domain: .diagnostics, pageID: "evaluation")
        case .apiToken:
            return .page(domain: .api, pageID: "inbound-auth")
        }
    }
}

public struct DesktopSelectedObjectRoute: RawRepresentable, Equatable, Codable, Sendable {
    public let kind: DesktopSelectedObjectKind
    public let objectID: String

    public var rawValue: String {
        "\(kind.rawValue):\(objectID)"
    }

    public var defaultRoute: DesktopRouteActionTarget {
        kind.defaultRoute
    }

    public init(kind: DesktopSelectedObjectKind, objectID: String) {
        self.kind = kind
        self.objectID = objectID
    }

    public init?(rawValue: String) {
        let trimmed = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let delimiterIndex = trimmed.firstIndex(of: ":") else {
            return nil
        }
        let prefix = String(trimmed[..<delimiterIndex])
        let objectID = String(trimmed[trimmed.index(after: delimiterIndex)...])
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard objectID.isEmpty == false,
              let kind = DesktopSelectedObjectKind(routePrefix: prefix)
        else {
            return nil
        }
        self.init(kind: kind, objectID: objectID)
    }
}

extension DesktopSurface {
    init(paneVisibilityID rawValue: String) {
        switch Self.normalizedPaneVisibilityID(rawValue) {
        case "commandcenter":
            self = .commandCenter
        case "image":
            self = .image
        case "server", "servers":
            self = .server
        case "models":
            self = .models
        case "workflows":
            self = .workflows
        case "jobs":
            self = .jobs
        case "diagnostics":
            self = .diagnostics
        case "tools":
            self = .tools
        case "api":
            self = .api
        case "settings":
            self = .settings
        default:
            self = .chat
        }
    }

    var paneVisibilityID: String {
        switch self {
        case .chat:
            return "chat"
        case .commandCenter:
            return "commandCenter"
        case .image:
            return "image"
        case .server:
            return "server"
        case .models:
            return "models"
        case .workflows:
            return "workflows"
        case .jobs:
            return "jobs"
        case .diagnostics:
            return "diagnostics"
        case .tools:
            return "tools"
        case .api:
            return "api"
        case .settings:
            return "settings"
        }
    }

    private static func normalizedPaneVisibilityID(_ rawValue: String) -> String {
        rawValue
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .filter(\.isLetter)
    }
}

@MainActor
public enum DesktopWorkspaceCommand: Equatable, Sendable {
    case selectSurface(DesktopSurface)
    case selectToolSection(DesktopToolSection)
    case openCommandCenter

    public func perform(on viewModel: RuntimeViewModel) {
        switch self {
        case .selectSurface(let surface):
            viewModel.selectSurface(surface)
        case .selectToolSection(let section):
            viewModel.selectToolSection(section)
        case .openCommandCenter:
            viewModel.openCommandCenter()
        }
    }
}

public enum DesktopServerAuthMode: String, CaseIterable, Identifiable, Codable, Sendable {
    case none = "None"
    case bearerToken = "Bearer Token"
    case apiKeys = "API Keys"

    public var id: String {
        rawValue
    }
}

public enum DesktopSharedAccessState: String, Codable, Sendable {
    case localOnly = "Local Only"
    case configuredDisabled = "Configured, Disabled"
    case enabled = "Enabled"
}

public enum DesktopServerSessionLifecycle: String, Codable, Sendable {
    case draft = "Draft"
    case starting = "Starting"
    case running = "Running"
    case paused = "Paused"
    case sleeping = "Sleeping"
    case stopping = "Stopping"
    case stopped = "Stopped"
    case error = "Error"
    case unavailable = "Unavailable"
}

public enum DesktopServerPowerState: String, Codable, Sendable {
    case active = "Active"
    case lightSleep = "Light Sleep"
    case deepSleep = "Deep Sleep"
    case stopped = "Stopped"
    case unavailable = "Unavailable"
}

public enum DesktopServerWakeReason: String, Codable, Sendable {
    case unspecified = "Unspecified"
    case initialBoot = "Initial Boot"
    case operatorResume = "Operator Resume"
    case requestActivity = "Request Activity"
    case toolActivity = "Tool Activity"
    case policyApply = "Policy Apply"
}

public struct DesktopServerServingDefaultsState: Codable, Equatable, Sendable {
    public var temperature: Double
    public var topP: Double
    public var maxTokens: Int
    public var streamIntervalTokens: Int
    public var maxConcurrentRequests: Int
    public var concurrentProcessingEnabled: Bool
    public var prefillBatchSize: Int
    public var completionBatchSize: Int
    public var accelerationProfile: String
    public var accelerationMode: String
    public var draftModelID: String
    public var numDraftTokens: Int
    public var effectiveTemperature: Double
    public var effectiveTopP: Double
    public var effectiveMaxTokens: Int
    public var effectiveStreamIntervalTokens: Int
    public var effectiveMaxConcurrentRequests: Int
    public var effectiveConcurrentProcessingEnabled: Bool
    public var effectivePrefillBatchSize: Int
    public var effectiveCompletionBatchSize: Int
    public var effectiveAccelerationProfile: String
    public var accelerationProfileIntent: String
    public var effectiveAccelerationMode: String
    public var effectiveDraftModelID: String
    public var effectiveNumDraftTokens: Int
    public var sourceText: String
    public var modelOverrideApplied: Bool
    public var updatedAtUnixMS: Int64

    public init(
        temperature: Double = 0.7,
        topP: Double = 1.0,
        maxTokens: Int = 256,
        streamIntervalTokens: Int = 1,
        maxConcurrentRequests: Int = 4,
        concurrentProcessingEnabled: Bool = true,
        prefillBatchSize: Int = 2,
        completionBatchSize: Int = 2,
        accelerationProfile: String = ServingAccelerationProfiles.defaultProfileID,
        accelerationMode: String = "baseline",
        draftModelID: String = "",
        numDraftTokens: Int = 0,
        effectiveTemperature: Double? = nil,
        effectiveTopP: Double? = nil,
        effectiveMaxTokens: Int? = nil,
        effectiveStreamIntervalTokens: Int? = nil,
        effectiveMaxConcurrentRequests: Int? = nil,
        effectiveConcurrentProcessingEnabled: Bool? = nil,
        effectivePrefillBatchSize: Int? = nil,
        effectiveCompletionBatchSize: Int? = nil,
        effectiveAccelerationProfile: String? = nil,
        accelerationProfileIntent: String = "",
        effectiveAccelerationMode: String? = nil,
        effectiveDraftModelID: String? = nil,
        effectiveNumDraftTokens: Int? = nil,
        sourceText: String = "Built-in Defaults",
        modelOverrideApplied: Bool = false,
        updatedAtUnixMS: Int64 = 0
    ) {
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
        self.streamIntervalTokens = streamIntervalTokens
        self.maxConcurrentRequests = maxConcurrentRequests
        self.concurrentProcessingEnabled = concurrentProcessingEnabled
        self.prefillBatchSize = prefillBatchSize
        self.completionBatchSize = completionBatchSize
        self.accelerationProfile = ServingAccelerationProfiles.normalizeProfileID(accelerationProfile)
            ?? ServingAccelerationProfiles.defaultProfileID
        self.accelerationMode = accelerationMode
        self.draftModelID = draftModelID
        self.numDraftTokens = numDraftTokens
        self.effectiveTemperature = effectiveTemperature ?? temperature
        self.effectiveTopP = effectiveTopP ?? topP
        self.effectiveMaxTokens = effectiveMaxTokens ?? maxTokens
        self.effectiveStreamIntervalTokens = effectiveStreamIntervalTokens ?? streamIntervalTokens
        self.effectiveMaxConcurrentRequests = effectiveMaxConcurrentRequests ?? maxConcurrentRequests
        self.effectiveConcurrentProcessingEnabled = effectiveConcurrentProcessingEnabled ?? concurrentProcessingEnabled
        self.effectivePrefillBatchSize = effectivePrefillBatchSize ?? prefillBatchSize
        self.effectiveCompletionBatchSize = effectiveCompletionBatchSize ?? completionBatchSize
        self.effectiveAccelerationProfile = ServingAccelerationProfiles.normalizeProfileID(effectiveAccelerationProfile)
            ?? self.accelerationProfile
        self.accelerationProfileIntent = accelerationProfileIntent.isEmpty
            ? ServingAccelerationProfiles.profile(id: self.effectiveAccelerationProfile).intent
            : accelerationProfileIntent
        self.effectiveAccelerationMode = effectiveAccelerationMode ?? accelerationMode
        self.effectiveDraftModelID = effectiveDraftModelID ?? draftModelID
        self.effectiveNumDraftTokens = effectiveNumDraftTokens ?? numDraftTokens
        self.sourceText = sourceText
        self.modelOverrideApplied = modelOverrideApplied
        self.updatedAtUnixMS = updatedAtUnixMS
    }

    enum CodingKeys: String, CodingKey {
        case temperature
        case topP = "top_p"
        case maxTokens = "max_tokens"
        case streamIntervalTokens = "stream_interval_tokens"
        case maxConcurrentRequests = "max_concurrent_requests"
        case concurrentProcessingEnabled = "concurrent_processing_enabled"
        case prefillBatchSize = "prefill_batch_size"
        case completionBatchSize = "completion_batch_size"
        case accelerationProfile = "acceleration_profile"
        case accelerationMode = "acceleration_mode"
        case draftModelID = "draft_model_id"
        case numDraftTokens = "num_draft_tokens"
        case effectiveTemperature = "effective_temperature"
        case effectiveTopP = "effective_top_p"
        case effectiveMaxTokens = "effective_max_tokens"
        case effectiveStreamIntervalTokens = "effective_stream_interval_tokens"
        case effectiveMaxConcurrentRequests = "effective_max_concurrent_requests"
        case effectiveConcurrentProcessingEnabled = "effective_concurrent_processing_enabled"
        case effectivePrefillBatchSize = "effective_prefill_batch_size"
        case effectiveCompletionBatchSize = "effective_completion_batch_size"
        case effectiveAccelerationProfile = "effective_acceleration_profile"
        case accelerationProfileIntent = "acceleration_profile_intent"
        case effectiveAccelerationMode = "effective_acceleration_mode"
        case effectiveDraftModelID = "effective_draft_model_id"
        case effectiveNumDraftTokens = "effective_num_draft_tokens"
        case sourceText = "source_text"
        case modelOverrideApplied = "model_override_applied"
        case updatedAtUnixMS = "updated_at_unix_ms"
    }

    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let temperature = try container.decodeIfPresent(Double.self, forKey: .temperature) ?? 0.7
        let topP = try container.decodeIfPresent(Double.self, forKey: .topP) ?? 1.0
        let maxTokens = try container.decodeIfPresent(Int.self, forKey: .maxTokens) ?? 256
        let streamIntervalTokens = try container.decodeIfPresent(Int.self, forKey: .streamIntervalTokens) ?? 1
        let maxConcurrentRequests = try container.decodeIfPresent(Int.self, forKey: .maxConcurrentRequests) ?? 4
        let concurrentProcessingEnabled = try container.decodeIfPresent(Bool.self, forKey: .concurrentProcessingEnabled) ?? true
        let prefillBatchSize = try container.decodeIfPresent(Int.self, forKey: .prefillBatchSize) ?? 2
        let completionBatchSize = try container.decodeIfPresent(Int.self, forKey: .completionBatchSize) ?? 2
        let accelerationProfile = try container.decodeIfPresent(String.self, forKey: .accelerationProfile)
            ?? ServingAccelerationProfiles.defaultProfileID
        let accelerationMode = try container.decodeIfPresent(String.self, forKey: .accelerationMode) ?? "baseline"
        let draftModelID = try container.decodeIfPresent(String.self, forKey: .draftModelID) ?? ""
        let numDraftTokens = try container.decodeIfPresent(Int.self, forKey: .numDraftTokens) ?? 0
        self.init(
            temperature: temperature,
            topP: topP,
            maxTokens: maxTokens,
            streamIntervalTokens: streamIntervalTokens,
            maxConcurrentRequests: maxConcurrentRequests,
            concurrentProcessingEnabled: concurrentProcessingEnabled,
            prefillBatchSize: prefillBatchSize,
            completionBatchSize: completionBatchSize,
            accelerationProfile: accelerationProfile,
            accelerationMode: accelerationMode,
            draftModelID: draftModelID,
            numDraftTokens: numDraftTokens,
            effectiveTemperature: try container.decodeIfPresent(Double.self, forKey: .effectiveTemperature),
            effectiveTopP: try container.decodeIfPresent(Double.self, forKey: .effectiveTopP),
            effectiveMaxTokens: try container.decodeIfPresent(Int.self, forKey: .effectiveMaxTokens),
            effectiveStreamIntervalTokens: try container.decodeIfPresent(Int.self, forKey: .effectiveStreamIntervalTokens),
            effectiveMaxConcurrentRequests: try container.decodeIfPresent(Int.self, forKey: .effectiveMaxConcurrentRequests),
            effectiveConcurrentProcessingEnabled: try container.decodeIfPresent(Bool.self, forKey: .effectiveConcurrentProcessingEnabled),
            effectivePrefillBatchSize: try container.decodeIfPresent(Int.self, forKey: .effectivePrefillBatchSize),
            effectiveCompletionBatchSize: try container.decodeIfPresent(Int.self, forKey: .effectiveCompletionBatchSize),
            effectiveAccelerationProfile: try container.decodeIfPresent(String.self, forKey: .effectiveAccelerationProfile),
            accelerationProfileIntent: try container.decodeIfPresent(String.self, forKey: .accelerationProfileIntent) ?? "",
            effectiveAccelerationMode: try container.decodeIfPresent(String.self, forKey: .effectiveAccelerationMode),
            effectiveDraftModelID: try container.decodeIfPresent(String.self, forKey: .effectiveDraftModelID),
            effectiveNumDraftTokens: try container.decodeIfPresent(Int.self, forKey: .effectiveNumDraftTokens),
            sourceText: try container.decodeIfPresent(String.self, forKey: .sourceText) ?? "Built-in Defaults",
            modelOverrideApplied: try container.decodeIfPresent(Bool.self, forKey: .modelOverrideApplied) ?? false,
            updatedAtUnixMS: try container.decodeIfPresent(Int64.self, forKey: .updatedAtUnixMS) ?? 0
        )
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(temperature, forKey: .temperature)
        try container.encode(topP, forKey: .topP)
        try container.encode(maxTokens, forKey: .maxTokens)
        try container.encode(streamIntervalTokens, forKey: .streamIntervalTokens)
        try container.encode(maxConcurrentRequests, forKey: .maxConcurrentRequests)
        try container.encode(concurrentProcessingEnabled, forKey: .concurrentProcessingEnabled)
        try container.encode(prefillBatchSize, forKey: .prefillBatchSize)
        try container.encode(completionBatchSize, forKey: .completionBatchSize)
        try container.encode(accelerationProfile, forKey: .accelerationProfile)
        try container.encode(accelerationMode, forKey: .accelerationMode)
        try container.encode(draftModelID, forKey: .draftModelID)
        try container.encode(numDraftTokens, forKey: .numDraftTokens)
        try container.encode(effectiveTemperature, forKey: .effectiveTemperature)
        try container.encode(effectiveTopP, forKey: .effectiveTopP)
        try container.encode(effectiveMaxTokens, forKey: .effectiveMaxTokens)
        try container.encode(effectiveStreamIntervalTokens, forKey: .effectiveStreamIntervalTokens)
        try container.encode(effectiveMaxConcurrentRequests, forKey: .effectiveMaxConcurrentRequests)
        try container.encode(effectiveConcurrentProcessingEnabled, forKey: .effectiveConcurrentProcessingEnabled)
        try container.encode(effectivePrefillBatchSize, forKey: .effectivePrefillBatchSize)
        try container.encode(effectiveCompletionBatchSize, forKey: .effectiveCompletionBatchSize)
        try container.encode(effectiveAccelerationProfile, forKey: .effectiveAccelerationProfile)
        try container.encode(accelerationProfileIntent, forKey: .accelerationProfileIntent)
        try container.encode(effectiveAccelerationMode, forKey: .effectiveAccelerationMode)
        try container.encode(effectiveDraftModelID, forKey: .effectiveDraftModelID)
        try container.encode(effectiveNumDraftTokens, forKey: .effectiveNumDraftTokens)
        try container.encode(sourceText, forKey: .sourceText)
        try container.encode(modelOverrideApplied, forKey: .modelOverrideApplied)
        try container.encode(updatedAtUnixMS, forKey: .updatedAtUnixMS)
    }
}

public struct DesktopServerSessionState: Codable, Identifiable, Equatable, Sendable {
    public let id: String
    public var title: String
    public var defaultModelID: String
    public var servedModelIDs: [String]
    public var host: String
    public var port: Int
    public var effectiveHost: String
    public var effectivePort: Int
    public var gatewayConfigSourceText: String
    public var gatewayConfigActiveBinding: Bool
    public var gatewayConfigRequiresRestart: Bool
    public var authMode: DesktopServerAuthMode
    public var authTokenHint: String
    public var sharedAccessState: DesktopSharedAccessState
    public var accessKeyCount: Int
    public var accessKeyHints: [String]
    public var rateLimitPerMinute: Int
    public var timeoutSeconds: Int
    public var modelIdleTimeoutSeconds: Int
    public var servingDefaults: DesktopServerServingDefaultsState
    public var lifecycle: DesktopServerSessionLifecycle
    public var powerState: DesktopServerPowerState
    public var wakeReason: DesktopServerWakeReason
    public var idleTimerSeconds: Int
    public var autoSleepEnabled: Bool
    public var lightSleepAfterSeconds: Int
    public var deepSleepAfterSeconds: Int
    public var requestedDiskStreamingModeText: String?
    public var effectiveDiskStreamingModeText: String?
    public var lastError: String
    public var lastKnownModelStateText: String
    public var activeAuthSessionCount: Int
    public var rememberedAuthSessionCount: Int
    public var expiredRememberedSessionCount: Int
    public var authSessionRetentionSeconds: Int
    public var lastAuthSessionSignOutLatencyMs: Double
    public var createdAt: Date
    public var updatedAt: Date

    public var modelID: String {
        get { defaultModelID }
        set {
            let resolvedDefaultModelID = Self.trimmed(newValue)
            defaultModelID = resolvedDefaultModelID
            servedModelIDs = resolvedDefaultModelID.isEmpty ? [] : [resolvedDefaultModelID]
        }
    }

    public init(
        id: String,
        title: String,
        modelID: String,
        servedModelIDs: [String] = [],
        host: String = MelixGatewayDefaults.host,
        port: Int = MelixGatewayDefaults.port,
        effectiveHost: String? = nil,
        effectivePort: Int? = nil,
        gatewayConfigSourceText: String = "Built-in Defaults",
        gatewayConfigActiveBinding: Bool = false,
        gatewayConfigRequiresRestart: Bool = false,
        authMode: DesktopServerAuthMode = .none,
        authTokenHint: String = "",
        sharedAccessState: DesktopSharedAccessState = .localOnly,
        accessKeyCount: Int = 0,
        accessKeyHints: [String] = [],
        rateLimitPerMinute: Int = 120,
        timeoutSeconds: Int = 120,
        modelIdleTimeoutSeconds: Int = 600,
        servingDefaults: DesktopServerServingDefaultsState = DesktopServerServingDefaultsState(),
        lifecycle: DesktopServerSessionLifecycle = .draft,
        powerState: DesktopServerPowerState = .unavailable,
        wakeReason: DesktopServerWakeReason = .unspecified,
        idleTimerSeconds: Int = 0,
        autoSleepEnabled: Bool = false,
        lightSleepAfterSeconds: Int = 0,
        deepSleepAfterSeconds: Int = 0,
        requestedDiskStreamingModeText: String? = nil,
        effectiveDiskStreamingModeText: String? = nil,
        lastError: String = "",
        lastKnownModelStateText: String = "",
        activeAuthSessionCount: Int = 0,
        rememberedAuthSessionCount: Int = 0,
        expiredRememberedSessionCount: Int = 0,
        authSessionRetentionSeconds: Int = 0,
        lastAuthSessionSignOutLatencyMs: Double = 0,
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.title = title
        let resolvedDefaultModelID = Self.trimmed(modelID)
        self.defaultModelID = resolvedDefaultModelID
        self.servedModelIDs = MelixServerModelRosterNormalizer.normalizedOrDefault(
            servedModelIDs,
            defaultModelID: resolvedDefaultModelID
        )
        self.host = host
        self.port = port
        self.effectiveHost = effectiveHost ?? host
        self.effectivePort = effectivePort ?? port
        self.gatewayConfigSourceText = gatewayConfigSourceText
        self.gatewayConfigActiveBinding = gatewayConfigActiveBinding
        self.gatewayConfigRequiresRestart = gatewayConfigRequiresRestart
        self.authMode = authMode
        self.authTokenHint = authTokenHint
        self.sharedAccessState = sharedAccessState
        self.accessKeyCount = accessKeyCount
        self.accessKeyHints = accessKeyHints
        self.rateLimitPerMinute = rateLimitPerMinute
        self.timeoutSeconds = timeoutSeconds
        self.modelIdleTimeoutSeconds = modelIdleTimeoutSeconds
        self.servingDefaults = servingDefaults
        self.lifecycle = lifecycle
        self.powerState = powerState
        self.wakeReason = wakeReason
        self.idleTimerSeconds = idleTimerSeconds
        self.autoSleepEnabled = autoSleepEnabled
        self.lightSleepAfterSeconds = lightSleepAfterSeconds
        self.deepSleepAfterSeconds = deepSleepAfterSeconds
        self.requestedDiskStreamingModeText = requestedDiskStreamingModeText
        self.effectiveDiskStreamingModeText = effectiveDiskStreamingModeText
        self.lastError = lastError
        self.lastKnownModelStateText = lastKnownModelStateText
        self.activeAuthSessionCount = activeAuthSessionCount
        self.rememberedAuthSessionCount = rememberedAuthSessionCount
        self.expiredRememberedSessionCount = expiredRememberedSessionCount
        self.authSessionRetentionSeconds = authSessionRetentionSeconds
        self.lastAuthSessionSignOutLatencyMs = lastAuthSessionSignOutLatencyMs
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }

    private static func trimmed(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    public var baseURL: String {
        "http://\(host):\(port)/v1"
    }

    public var effectiveBaseURL: String {
        "http://\(effectiveHost):\(effectivePort)/v1"
    }

    public var integrationAuthValue: String {
        switch authMode {
        case .none:
            return "not-required"
        case .bearerToken:
            let placeholder = authTokenHint.isEmpty ? "melix-api-key" : authTokenHint
            return "<\(placeholder)>"
        case .apiKeys:
            let placeholder = authTokenHint.isEmpty
                ? (accessKeyHints.first ?? "melix-shared-key")
                : authTokenHint
            return "<\(placeholder)>"
        }
    }

    public var accessKeyHintsText: String {
        accessKeyHints.isEmpty ? "No key hints configured." : accessKeyHints.joined(separator: ", ")
    }

    public var sharedAccessSummaryText: String {
        switch sharedAccessState {
        case .localOnly:
            return "Local trust only."
        case .configuredDisabled:
            return "Shared access is configured but disabled."
        case .enabled:
            let suffix = accessKeyCount == 1 ? "key" : "keys"
            return "Shared access is enabled for \(accessKeyCount) \(suffix)."
        }
    }

    public var listenerLabel: String {
        "\(host):\(port)"
    }

    public var effectiveListenerLabel: String {
        "\(effectiveHost):\(effectivePort)"
    }

    public var isRunning: Bool {
        lifecycle == .running
    }

    public var persistentSessionSummaryText: String {
        let retentionText = authSessionRetentionSeconds > 0 ? " TTL \(authSessionRetentionSeconds)s." : ""
        if rememberedAuthSessionCount > 0 {
            let expiredText = expiredRememberedSessionCount > 0
                ? " \(expiredRememberedSessionCount) expired pruned."
                : ""
            return "\(rememberedAuthSessionCount) remembered sessions active, \(activeAuthSessionCount) total active.\(expiredText)\(retentionText)"
        }
        if activeAuthSessionCount > 0 {
            return "\(activeAuthSessionCount) gateway sessions active.\(retentionText)"
        }
        return "No remembered gateway sessions.\(retentionText)"
    }

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case modelID = "model_id"
        case defaultModelID = "default_model_id"
        case servedModelIDs = "served_model_ids"
        case host
        case port
        case effectiveHost = "effective_host"
        case effectivePort = "effective_port"
        case gatewayConfigSourceText = "gateway_config_source_text"
        case gatewayConfigActiveBinding = "gateway_config_active_binding"
        case gatewayConfigRequiresRestart = "gateway_config_requires_restart"
        case authMode = "auth_mode"
        case authTokenHint = "auth_token_hint"
        case sharedAccessState = "shared_access_state"
        case accessKeyCount = "access_key_count"
        case accessKeyHints = "access_key_hints"
        case rateLimitPerMinute = "rate_limit_per_minute"
        case timeoutSeconds = "timeout_seconds"
        case modelIdleTimeoutSeconds = "model_idle_timeout_seconds"
        case servingDefaults = "serving_defaults"
        case lifecycle
        case powerState = "power_state"
        case wakeReason = "wake_reason"
        case idleTimerSeconds = "idle_timer_seconds"
        case autoSleepEnabled = "auto_sleep_enabled"
        case lightSleepAfterSeconds = "light_sleep_after_seconds"
        case deepSleepAfterSeconds = "deep_sleep_after_seconds"
        case lastError = "last_error"
        case lastKnownModelStateText = "last_known_model_state_text"
        case activeAuthSessionCount = "active_auth_session_count"
        case rememberedAuthSessionCount = "remembered_auth_session_count"
        case expiredRememberedSessionCount = "expired_remembered_session_count"
        case authSessionRetentionSeconds = "auth_session_retention_seconds"
        case lastAuthSessionSignOutLatencyMs = "last_auth_session_sign_out_latency_ms"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        title = try container.decode(String.self, forKey: .title)
        let decodedDefaultModelID = try container.decodeIfPresent(String.self, forKey: .defaultModelID)
            ?? (try container.decodeIfPresent(String.self, forKey: .modelID) ?? "")
        defaultModelID = Self.trimmed(decodedDefaultModelID)
        servedModelIDs = MelixServerModelRosterNormalizer.normalized(
            try container.decodeIfPresent([String].self, forKey: .servedModelIDs)
                ?? (defaultModelID.isEmpty ? [] : [defaultModelID]),
            defaultModelID: defaultModelID
        )
        host = try container.decodeIfPresent(String.self, forKey: .host) ?? MelixGatewayDefaults.host
        port = try container.decodeIfPresent(Int.self, forKey: .port) ?? MelixGatewayDefaults.port
        effectiveHost = try container.decodeIfPresent(String.self, forKey: .effectiveHost) ?? host
        effectivePort = try container.decodeIfPresent(Int.self, forKey: .effectivePort) ?? port
        gatewayConfigSourceText = try container.decodeIfPresent(String.self, forKey: .gatewayConfigSourceText)
            ?? "Built-in Defaults"
        gatewayConfigActiveBinding = try container.decodeIfPresent(Bool.self, forKey: .gatewayConfigActiveBinding) ?? false
        gatewayConfigRequiresRestart = try container.decodeIfPresent(Bool.self, forKey: .gatewayConfigRequiresRestart) ?? false
        authMode = try container.decodeIfPresent(DesktopServerAuthMode.self, forKey: .authMode) ?? .none
        authTokenHint = try container.decodeIfPresent(String.self, forKey: .authTokenHint) ?? ""
        sharedAccessState = try container.decodeIfPresent(DesktopSharedAccessState.self, forKey: .sharedAccessState) ?? .localOnly
        accessKeyCount = try container.decodeIfPresent(Int.self, forKey: .accessKeyCount) ?? 0
        accessKeyHints = try container.decodeIfPresent([String].self, forKey: .accessKeyHints) ?? []
        rateLimitPerMinute = try container.decodeIfPresent(Int.self, forKey: .rateLimitPerMinute) ?? 120
        timeoutSeconds = try container.decodeIfPresent(Int.self, forKey: .timeoutSeconds) ?? 120
        modelIdleTimeoutSeconds = try container.decodeIfPresent(Int.self, forKey: .modelIdleTimeoutSeconds) ?? 600
        servingDefaults = try container.decodeIfPresent(DesktopServerServingDefaultsState.self, forKey: .servingDefaults)
            ?? DesktopServerServingDefaultsState()
        lifecycle = try container.decodeIfPresent(DesktopServerSessionLifecycle.self, forKey: .lifecycle) ?? .draft
        powerState = try container.decodeIfPresent(DesktopServerPowerState.self, forKey: .powerState) ?? .unavailable
        wakeReason = try container.decodeIfPresent(DesktopServerWakeReason.self, forKey: .wakeReason) ?? .unspecified
        idleTimerSeconds = try container.decodeIfPresent(Int.self, forKey: .idleTimerSeconds) ?? 0
        autoSleepEnabled = try container.decodeIfPresent(Bool.self, forKey: .autoSleepEnabled) ?? false
        lightSleepAfterSeconds = try container.decodeIfPresent(Int.self, forKey: .lightSleepAfterSeconds) ?? 0
        deepSleepAfterSeconds = try container.decodeIfPresent(Int.self, forKey: .deepSleepAfterSeconds) ?? 0
        lastError = try container.decodeIfPresent(String.self, forKey: .lastError) ?? ""
        lastKnownModelStateText = try container.decodeIfPresent(String.self, forKey: .lastKnownModelStateText) ?? ""
        activeAuthSessionCount = try container.decodeIfPresent(Int.self, forKey: .activeAuthSessionCount) ?? 0
        rememberedAuthSessionCount = try container.decodeIfPresent(Int.self, forKey: .rememberedAuthSessionCount) ?? 0
        expiredRememberedSessionCount = try container.decodeIfPresent(Int.self, forKey: .expiredRememberedSessionCount) ?? 0
        authSessionRetentionSeconds = try container.decodeIfPresent(Int.self, forKey: .authSessionRetentionSeconds) ?? 0
        lastAuthSessionSignOutLatencyMs = try container.decodeIfPresent(Double.self, forKey: .lastAuthSessionSignOutLatencyMs) ?? 0
        createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
        updatedAt = try container.decodeIfPresent(Date.self, forKey: .updatedAt) ?? Date()
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(title, forKey: .title)
        try container.encode(defaultModelID, forKey: .defaultModelID)
        try container.encode(servedModelIDs, forKey: .servedModelIDs)
        try container.encode(host, forKey: .host)
        try container.encode(port, forKey: .port)
        try container.encode(effectiveHost, forKey: .effectiveHost)
        try container.encode(effectivePort, forKey: .effectivePort)
        try container.encode(gatewayConfigSourceText, forKey: .gatewayConfigSourceText)
        try container.encode(gatewayConfigActiveBinding, forKey: .gatewayConfigActiveBinding)
        try container.encode(gatewayConfigRequiresRestart, forKey: .gatewayConfigRequiresRestart)
        try container.encode(authMode, forKey: .authMode)
        try container.encode(authTokenHint, forKey: .authTokenHint)
        try container.encode(sharedAccessState, forKey: .sharedAccessState)
        try container.encode(accessKeyCount, forKey: .accessKeyCount)
        try container.encode(accessKeyHints, forKey: .accessKeyHints)
        try container.encode(rateLimitPerMinute, forKey: .rateLimitPerMinute)
        try container.encode(timeoutSeconds, forKey: .timeoutSeconds)
        try container.encode(modelIdleTimeoutSeconds, forKey: .modelIdleTimeoutSeconds)
        try container.encode(servingDefaults, forKey: .servingDefaults)
        try container.encode(lifecycle, forKey: .lifecycle)
        try container.encode(powerState, forKey: .powerState)
        try container.encode(wakeReason, forKey: .wakeReason)
        try container.encode(idleTimerSeconds, forKey: .idleTimerSeconds)
        try container.encode(autoSleepEnabled, forKey: .autoSleepEnabled)
        try container.encode(lightSleepAfterSeconds, forKey: .lightSleepAfterSeconds)
        try container.encode(deepSleepAfterSeconds, forKey: .deepSleepAfterSeconds)
        try container.encode(lastError, forKey: .lastError)
        try container.encode(lastKnownModelStateText, forKey: .lastKnownModelStateText)
        try container.encode(activeAuthSessionCount, forKey: .activeAuthSessionCount)
        try container.encode(rememberedAuthSessionCount, forKey: .rememberedAuthSessionCount)
        try container.encode(expiredRememberedSessionCount, forKey: .expiredRememberedSessionCount)
        try container.encode(authSessionRetentionSeconds, forKey: .authSessionRetentionSeconds)
        try container.encode(lastAuthSessionSignOutLatencyMs, forKey: .lastAuthSessionSignOutLatencyMs)
        try container.encode(createdAt, forKey: .createdAt)
        try container.encode(updatedAt, forKey: .updatedAt)
    }
}

public struct DesktopChatSessionState: Identifiable, Equatable, Sendable {
    public let id: String
    public var title: String
    public var serverSessionID: String
    public var branchID: String
    public var branchTitle: String
    public var transcript: [DesktopChatTranscriptEntry]
    public var statusText: String
    public var usageText: String
    public var requestID: String
    public var isStreaming: Bool
    public var exportPath: String
    public var createdAt: Date
    public var updatedAt: Date

    public init(
        id: String,
        title: String,
        serverSessionID: String,
        branchID: String = "main",
        branchTitle: String = "Main",
        transcript: [DesktopChatTranscriptEntry] = [],
        statusText: String = "Idle",
        usageText: String = "",
        requestID: String = "",
        isStreaming: Bool = false,
        exportPath: String = "",
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.title = title
        self.serverSessionID = serverSessionID
        self.branchID = branchID
        self.branchTitle = branchTitle
        self.transcript = transcript
        self.statusText = statusText
        self.usageText = usageText
        self.requestID = requestID
        self.isStreaming = isStreaming
        self.exportPath = exportPath
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }

    public var summaryText: String {
        transcript.last?.body.isEmpty == false ? transcript.last?.body ?? "" : statusText
    }

    public var hasServerBinding: Bool {
        serverSessionID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
    }

    public var displayBranchTitle: String? {
        let trimmedTitle = branchTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmedTitle.isEmpty == false else {
            return nil
        }
        guard branchID != "main" else {
            return nil
        }
        return trimmedTitle
    }
}

public enum DesktopBannerSeverity: Sendable {
    case info
    case warning
    case critical
}

public enum DesktopSignalPriority: Int, Comparable, Sendable {
    case info = 0
    case recovery = 10
    case warning = 20
    case critical = 30

    public static func < (lhs: DesktopSignalPriority, rhs: DesktopSignalPriority) -> Bool {
        lhs.rawValue < rhs.rawValue
    }
}

public struct DesktopBannerState: Equatable, Sendable {
    public let id: String
    public let title: String
    public let detail: String
    public let severity: DesktopBannerSeverity
    public let isDismissible: Bool
    public let isRecoverable: Bool

    public init(
        id: String = "",
        title: String,
        detail: String,
        severity: DesktopBannerSeverity,
        isDismissible: Bool = false,
        isRecoverable: Bool = false
    ) {
        self.id = id.isEmpty ? Self.defaultID(title: title, detail: detail, severity: severity) : id
        self.title = title
        self.detail = detail
        self.severity = severity
        self.isDismissible = isDismissible
        self.isRecoverable = isRecoverable
    }

    private static func defaultID(
        title: String,
        detail: String,
        severity: DesktopBannerSeverity
    ) -> String {
        let severityKey: String = switch severity {
        case .info:
            "info"
        case .warning:
            "warning"
        case .critical:
            "critical"
        }
        return "\(severityKey)-\(title)-\(detail)"
    }

    public var priority: DesktopSignalPriority {
        switch severity {
        case .critical:
            return .critical
        case .warning:
            return isRecoverable ? .recovery : .warning
        case .info:
            return .info
        }
    }
}

public extension DesktopServerSessionState {
    var isInteractiveReady: Bool {
        lifecycle == .running || lifecycle == .sleeping
    }

    var retainsGatewayAccessConfiguration: Bool {
        switch lifecycle {
        case .starting, .running, .paused, .sleeping:
            return true
        default:
            return false
        }
    }

    var canStart: Bool {
        switch lifecycle {
        case .draft, .stopped, .error, .unavailable:
            return true
        default:
            return false
        }
    }

    var canPause: Bool {
        lifecycle == .running
    }

    var canResume: Bool {
        lifecycle == .paused
    }

    var canWake: Bool {
        lifecycle == .sleeping
    }

    var canStop: Bool {
        switch lifecycle {
        case .starting, .running, .paused, .sleeping, .error:
            return true
        default:
            return false
        }
    }

    var lifecycleSummaryText: String {
        "\(lifecycle.rawValue) • \(powerState.rawValue)"
    }

    var idlePolicySummaryText: String {
        guard autoSleepEnabled else {
            return "Auto sleep disabled."
        }

        let lightSummary = lightSleepAfterSeconds > 0 ? "light after \(lightSleepAfterSeconds)s" : "light sleep threshold unset"
        let deepSummary = deepSleepAfterSeconds > 0 ? "deep after \(deepSleepAfterSeconds)s" : "deep sleep threshold unset"
        return "Auto sleep enabled • \(lightSummary) • \(deepSummary)"
    }

    var runtimeDetailText: String {
        let idleSummary = idleTimerSeconds > 0 ? "Idle \(idleTimerSeconds)s" : "Idle timer idle"
        var parts = [
            lifecycleSummaryText,
            "Wake \(wakeReason.rawValue)",
            idleSummary,
        ]
        if let requestedDiskStreamingModeText, !requestedDiskStreamingModeText.isEmpty,
           let effectiveDiskStreamingModeText, !effectiveDiskStreamingModeText.isEmpty {
            parts.append("Disk \(requestedDiskStreamingModeText) -> \(effectiveDiskStreamingModeText)")
        }
        return parts.joined(separator: " • ")
    }

    var lifecycleBannerState: DesktopBannerState? {
        switch lifecycle {
        case .draft:
            return nil
        case .starting:
            return DesktopBannerState(
                title: "\(title) Is Starting",
                detail: "Preparing \(listenerLabel) for \(modelID). Requests stay queued until the session reaches Running.",
                severity: .info
            )
        case .running:
            return nil
        case .paused:
            return DesktopBannerState(
                title: "\(title) Is Paused",
                detail: "Resume the session to accept prompts and API requests. \(idlePolicySummaryText)",
                severity: .warning
            )
        case .sleeping:
            return DesktopBannerState(
                title: "\(title) Is Sleeping",
                detail: "\(powerState.rawValue) mode is active. The next request can wake the session automatically, or you can wake it manually now.",
                severity: .info
            )
        case .stopping:
            return DesktopBannerState(
                title: "\(title) Is Stopping",
                detail: "Melix is draining the session and closing \(listenerLabel).",
                severity: .info
            )
        case .stopped:
            return DesktopBannerState(
                title: "\(title) Is Stopped",
                detail: "Start the session to serve \(modelID) at \(listenerLabel).",
                severity: .warning
            )
        case .error:
            return DesktopBannerState(
                title: "\(title) Needs Recovery",
                detail: lastError.isEmpty ? "The session entered an error state." : lastError,
                severity: .critical
            )
        case .unavailable:
            return DesktopBannerState(
                title: "\(title) Is Unavailable",
                detail: "Bind the session to an available text model before serving requests.",
                severity: .warning
            )
        }
    }

    var chatWorkspaceNoticeState: DesktopBannerState? {
        switch lifecycle {
        case .running:
            return nil
        case .sleeping:
            return DesktopBannerState(
                title: "\(title) Will Wake On Demand",
                detail: "You can send the next prompt immediately. Melix will wake the session from \(powerState.rawValue.lowercased()) first.",
                severity: .info
            )
        case .paused:
            return DesktopBannerState(
                title: "\(title) Is Paused",
                detail: "Resume the bound server session before sending prompts from this chat.",
                severity: .warning
            )
        case .starting:
            return DesktopBannerState(
                title: "\(title) Is Starting",
                detail: "Chat stays read-only until the server session finishes booting.",
                severity: .info
            )
        case .stopping:
            return DesktopBannerState(
                title: "\(title) Is Stopping",
                detail: "This chat stays read-only while the bound server session drains.",
                severity: .warning
            )
        case .stopped:
            return DesktopBannerState(
                title: "\(title) Is Stopped",
                detail: "Start the bound server session before sending prompts from this chat.",
                severity: .warning
            )
        case .error:
            return DesktopBannerState(
                title: "\(title) Needs Recovery",
                detail: lastError.isEmpty ? "The bound server session failed." : lastError,
                severity: .critical
            )
        case .draft, .unavailable:
            return DesktopBannerState(
                title: "No Active Server Session",
                detail: "Choose a valid server session and start it before sending prompts from this chat.",
                severity: .warning
            )
        }
    }
}
