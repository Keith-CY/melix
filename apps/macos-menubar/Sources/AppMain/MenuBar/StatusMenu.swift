import AppKit
import Foundation

public enum StatusMenuAction: String, Equatable, Sendable {
    case openCommandCenter
    case openConsole
    case openDownloads
    case openServer
    case resumeFirstDownload
    case startSelectedServer
    case wakeSelectedServer
    case loadPrimaryModel
    case unloadPrimaryModel
    case quit
}

public enum StatusMenuContentItem: Equatable, Sendable {
    case info(String)
    case action(String, StatusMenuAction)
    case error(String)
    case separator
}

public struct StatusMenuContent: Equatable, Sendable {
    public let title: String
    public let items: [StatusMenuContentItem]

    public init(title: String, items: [StatusMenuContentItem]) {
        self.title = title
        self.items = items
    }
}

@MainActor
public protocol StatusMenuRendering {
    func render(content: StatusMenuContent, target: AnyObject, action: Selector)
}

@MainActor
public final class AppKitStatusMenuRenderer: StatusMenuRendering {
    private let statusBar: NSStatusBar
    private let statusItem: NSStatusItem
    private static let maxInfoTitleLength = 44
    private static let maxErrorTitleLength = 44

    var currentStatusItem: NSStatusItem {
        statusItem
    }

    public init(statusBar: NSStatusBar = .system) {
        self.statusBar = statusBar
        self.statusItem = statusBar.statusItem(withLength: NSStatusItem.squareLength)
    }

    public func render(content: StatusMenuContent, target: AnyObject, action: Selector) {
        statusItem.button?.title = ""
        statusItem.button?.image = sizedTrayTemplateIcon()
        statusItem.button?.imagePosition = .imageOnly
        statusItem.button?.imageScaling = .scaleProportionallyUpOrDown
        statusItem.button?.toolTip = content.title
        statusItem.menu = Self.makeMenu(content: content, target: target, action: action)
    }

    private func sizedTrayTemplateIcon() -> NSImage {
        let baseImage = MelixBranding.trayTemplateIcon()
        let image = (baseImage.copy() as? NSImage) ?? baseImage
        let iconSide = max(14, floor(statusBar.thickness - 1))
        image.size = NSSize(width: iconSide, height: iconSide)
        return image
    }

    static func makeMenu(content: StatusMenuContent, target: AnyObject, action: Selector) -> NSMenu {
        let menu = NSMenu()
        for item in content.items {
            menu.addItem(makeMenuItem(item, target: target, action: action))
        }
        return menu
    }

    private static func makeMenuItem(
        _ item: StatusMenuContentItem,
        target: AnyObject,
        action: Selector
    ) -> NSMenuItem {
        switch item {
        case .info(let title):
            let displayTitle = compactInfoTitle(title)
            let menuItem = NSMenuItem(title: displayTitle, action: nil, keyEquivalent: "")
            menuItem.isEnabled = false
            menuItem.toolTip = displayTitle == title ? nil : title
            return menuItem
        case .action(let title, let menuAction):
            let menuItem = NSMenuItem(title: title, action: action, keyEquivalent: "")
            menuItem.target = target
            menuItem.representedObject = menuAction.rawValue
            return menuItem
        case .error(let message):
            let menuItem = NSMenuItem(title: compactErrorTitle(message), action: nil, keyEquivalent: "")
            menuItem.isEnabled = false
            menuItem.toolTip = "Error: \(message)"
            return menuItem
        case .separator:
            return .separator()
        }
    }

    private static func compactInfoTitle(_ title: String) -> String {
        compactMenuText(title, maxLength: maxInfoTitleLength)
    }

    private static func compactErrorTitle(_ message: String) -> String {
        let summary = message.split(separator: ":", maxSplits: 1).first.map(String.init) ?? message
        return "Error: \(compactMenuText(summary, maxLength: maxErrorTitleLength))"
    }

    private static func compactMenuText(_ text: String, maxLength: Int) -> String {
        guard text.count > maxLength else {
            return text
        }

        let endIndex = text.index(text.startIndex, offsetBy: maxLength)
        return String(text[..<endIndex]).trimmingCharacters(in: .whitespacesAndNewlines) + "…"
    }
}

@MainActor
public final class StatusMenu: NSObject {
    private let renderer: any StatusMenuRendering
    private let viewModel: RuntimeViewModel
    private let openConsoleHandler: @MainActor @Sendable () -> Void
    private let terminationHandler: @MainActor @Sendable () -> Void

    public init(
        viewModel: RuntimeViewModel,
        renderer: any StatusMenuRendering = AppKitStatusMenuRenderer(),
        openConsoleHandler: @escaping @MainActor @Sendable () -> Void = {},
        terminationHandler: @escaping @MainActor @Sendable () -> Void = { NSApplication.shared.terminate(nil) }
    ) {
        self.viewModel = viewModel
        self.renderer = renderer
        self.openConsoleHandler = openConsoleHandler
        self.terminationHandler = terminationHandler
        super.init()
    }

    public func install() {
        viewModel.onStateChanged = { [weak self] in
            self?.render()
        }
        render()
    }

    func content() -> StatusMenuContent {
        var items: [StatusMenuContentItem] = [
            .info("Server: \(viewModel.serverStateText)")
        ]

        for banner in viewModel.desktopSignalStates.prefix(3) {
            switch banner.severity {
            case .critical:
                items.append(.error(banner.title))
            case .info, .warning:
                items.append(.info(banner.title))
            }
        }

        appendRecoveryActions(to: &items)

        if let model = viewModel.primaryModel {
            items.append(.info("\(model.modelID): \(model.stateText)"))
            items.append(
                .action(
                    model.actionTitle,
                    model.isLoaded ? .unloadPrimaryModel : .loadPrimaryModel
                )
            )
        }

        items.append(.action("Open Command Center", .openCommandCenter))
        items.append(.action("Open Melix Console", .openConsole))

        if let lastError = viewModel.lastError {
            items.append(.error(lastError))
        }

        items.append(.separator)
        items.append(.action("Quit Melix", .quit))

        return StatusMenuContent(title: viewModel.statusTitle, items: items)
    }

    func perform(_ action: StatusMenuAction) {
        switch action {
        case .openCommandCenter:
            viewModel.openCommandCenter()
        case .openConsole:
            openConsoleHandler()
        case .openDownloads:
            viewModel.selectToolSection(.downloads)
        case .openServer:
            viewModel.selectSurface(.server)
        case .resumeFirstDownload:
            Task { @MainActor in
                if let download = viewModel.recoverableDownloads.first {
                    await viewModel.resumeDownload(jobID: download.jobID)
                }
            }
        case .startSelectedServer:
            Task { @MainActor in
                await viewModel.startSelectedServerSession()
            }
        case .wakeSelectedServer:
            Task { @MainActor in
                await viewModel.wakeSelectedServerSession()
            }
        case .loadPrimaryModel:
            Task { @MainActor in
                await viewModel.loadPrimaryModel()
            }
        case .unloadPrimaryModel:
            Task { @MainActor in
                await viewModel.unloadPrimaryModel()
            }
        case .quit:
            terminationHandler()
        }
    }

    private func render() {
        renderer.render(content: content(), target: self, action: #selector(handleMenuAction(_:)))
    }

    private func appendRecoveryActions(to items: inout [StatusMenuContentItem]) {
        if viewModel.recoverableDownloads.isEmpty == false {
            items.append(.action("Resume Download", .resumeFirstDownload))
            items.append(.action("Open Downloads", .openDownloads))
        } else if viewModel.activeDownloads.isEmpty == false {
            items.append(.action("Open Downloads", .openDownloads))
        }

        guard let session = viewModel.selectedServerSession else {
            return
        }
        switch session.lifecycle {
        case .sleeping:
            items.append(.action("Wake Server", .wakeSelectedServer))
            items.append(.action("Open Server", .openServer))
        case .stopped, .error, .unavailable:
            items.append(.action("Start Server", .startSelectedServer))
            items.append(.action("Open Server", .openServer))
        case .paused:
            items.append(.action("Open Server", .openServer))
        case .draft, .starting, .running, .stopping:
            break
        }
    }

    @objc func handleMenuAction(_ sender: NSMenuItem) {
        guard
            let rawValue = sender.representedObject as? String,
            let action = StatusMenuAction(rawValue: rawValue)
        else {
            return
        }

        perform(action)
    }
}
