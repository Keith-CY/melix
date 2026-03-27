import AppKit
import Foundation

public enum StatusMenuAction: String, Equatable, Sendable {
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
    private let statusItem: NSStatusItem

    var currentStatusItem: NSStatusItem {
        statusItem
    }

    public init(statusBar: NSStatusBar = .system) {
        self.statusItem = statusBar.statusItem(withLength: NSStatusItem.variableLength)
    }

    public func render(content: StatusMenuContent, target: AnyObject, action: Selector) {
        statusItem.button?.title = content.title
        statusItem.menu = Self.makeMenu(content: content, target: target, action: action)
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
            let menuItem = NSMenuItem(title: title, action: nil, keyEquivalent: "")
            menuItem.isEnabled = false
            return menuItem
        case .action(let title, let menuAction):
            let menuItem = NSMenuItem(title: title, action: action, keyEquivalent: "")
            menuItem.target = target
            menuItem.representedObject = menuAction.rawValue
            return menuItem
        case .error(let message):
            let menuItem = NSMenuItem(title: "Error: \(message)", action: nil, keyEquivalent: "")
            menuItem.isEnabled = false
            return menuItem
        case .separator:
            return .separator()
        }
    }
}

@MainActor
public final class StatusMenu: NSObject {
    private let renderer: any StatusMenuRendering
    private let viewModel: RuntimeViewModel
    private let terminationHandler: @MainActor @Sendable () -> Void

    public init(
        viewModel: RuntimeViewModel,
        renderer: any StatusMenuRendering = AppKitStatusMenuRenderer(),
        terminationHandler: @escaping @MainActor @Sendable () -> Void = { NSApplication.shared.terminate(nil) }
    ) {
        self.viewModel = viewModel
        self.renderer = renderer
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

        if let model = viewModel.primaryModel {
            items.append(.info("\(model.modelID): \(model.stateText)"))
            items.append(
                .action(
                    model.actionTitle,
                    model.isLoaded ? .unloadPrimaryModel : .loadPrimaryModel
                )
            )
        }

        if let lastError = viewModel.lastError {
            items.append(.error(lastError))
        }

        items.append(.separator)
        items.append(.action("Quit Melix", .quit))

        return StatusMenuContent(title: viewModel.statusTitle, items: items)
    }

    func perform(_ action: StatusMenuAction) {
        switch action {
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
