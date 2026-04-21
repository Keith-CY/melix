import SwiftUI

enum DesktopShellChromeMetrics {
    static let titleBarTabHeightBudget: CGFloat = 30
    static let titleBarTabHorizontalPadding: CGFloat = 9
    static let titleBarTabVerticalPadding: CGFloat = 4
    static let titleBarTabContainerInset: CGFloat = 3
    static let paneToggleButtonWidth: CGFloat = 28
    static let paneToggleButtonHeight: CGFloat = 24
}

enum DesktopWorkspacePaneAnimation {
    static let durationSeconds = 0.20
    static let animation = Animation.easeInOut(duration: durationSeconds)
}

enum DesktopWorkspacePaneTransition {
    static func edge(for role: DesktopPaneRole) -> Edge {
        switch role {
        case .sidebar:
            return .leading
        case .inspector:
            return .trailing
        }
    }

    static func transition(for role: DesktopPaneRole) -> AnyTransition {
        .move(edge: edge(for: role)).combined(with: .opacity)
    }
}

enum DesktopWorkspacePaneSlotMetrics {
    static let collapsedWidth: CGFloat = 0

    static func width(isVisible: Bool, idealWidth: CGFloat) -> CGFloat {
        isVisible ? idealWidth : collapsedWidth
    }

    static func alignment(for role: DesktopPaneRole) -> Alignment {
        switch role {
        case .sidebar:
            return .leading
        case .inspector:
            return .trailing
        }
    }
}

extension View {
    func desktopWorkspacePaneTransition(_ role: DesktopPaneRole) -> some View {
        transition(DesktopWorkspacePaneTransition.transition(for: role))
    }
}

struct DesktopWorkspacePaneSlot<Content: View>: View {
    let role: DesktopPaneRole
    let isVisible: Bool
    let idealWidth: CGFloat
    @ViewBuilder let content: () -> Content

    var body: some View {
        content()
            .frame(width: idealWidth, alignment: DesktopWorkspacePaneSlotMetrics.alignment(for: role))
            .opacity(isVisible ? 1 : 0)
            .accessibilityHidden(isVisible == false)
            .allowsHitTesting(isVisible)
            .frame(
                width: DesktopWorkspacePaneSlotMetrics.width(isVisible: isVisible, idealWidth: idealWidth),
                alignment: DesktopWorkspacePaneSlotMetrics.alignment(for: role)
            )
            .clipped()
    }
}

struct DesktopWorkspaceTitleBarTabsView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        DesktopShellTabStripView(
            selectedSurface: viewModel.selectedSurface,
            selectSurface: viewModel.selectSurface
        )
    }
}

struct DesktopWorkspaceTitleBarCommandCenterButton: View {
    static let symbolName = "command.circle"

    let openCommandCenter: () -> Void

    var body: some View {
        Button(action: openCommandCenter) {
            Image(systemName: Self.symbolName)
                .font(.title3.weight(.semibold))
                .frame(width: 28, height: 28)
                .contentShape(RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.md, style: .continuous))
        }
        .buttonStyle(.plain)
        .help("Open Command Center")
        .accessibilityLabel("Open Command Center")
        .keyboardShortcut("k", modifiers: .command)
        .fixedSize(horizontal: true, vertical: false)
    }
}

struct DesktopWorkspaceTitleBarActionsView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        HStack(spacing: 4) {
            DesktopPaneToggleButton(
                role: .sidebar,
                isVisible: viewModel.isDesktopPaneVisible(.sidebar)
            ) {
                withAnimation(DesktopWorkspacePaneAnimation.animation) {
                    viewModel.toggleDesktopPane(.sidebar)
                }
            }
            DesktopPaneToggleButton(
                role: .inspector,
                isVisible: viewModel.isDesktopPaneVisible(.inspector)
            ) {
                withAnimation(DesktopWorkspacePaneAnimation.animation) {
                    viewModel.toggleDesktopPane(.inspector)
                }
            }
            DesktopWorkspaceTitleBarCommandCenterButton(openCommandCenter: viewModel.openCommandCenter)
        }
        .fixedSize(horizontal: true, vertical: false)
    }
}

struct DesktopWorkspaceHeader<Trailing: View>: View {
    let title: String
    let subtitle: String?
    @ViewBuilder let trailing: () -> Trailing

    init(
        title: String,
        subtitle: String? = nil,
        @ViewBuilder trailing: @escaping () -> Trailing
    ) {
        self.title = title
        self.subtitle = subtitle
        self.trailing = trailing
    }

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.largeTitle.weight(.semibold))
                if let subtitle, subtitle.isEmpty == false {
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer(minLength: 12)
            trailing()
        }
    }
}

struct DesktopPaneToggleButton: View {
    let role: DesktopPaneRole
    let isVisible: Bool
    let action: () -> Void
    var shortcut: KeyboardShortcut?

    init(
        role: DesktopPaneRole,
        isVisible: Bool,
        shortcut: KeyboardShortcut? = nil,
        action: @escaping () -> Void
    ) {
        self.role = role
        self.isVisible = isVisible
        self.shortcut = shortcut
        self.action = action
    }

    var body: some View {
        let label = role.accessibilityLabel(isVisible: isVisible)
        let button = Button(action: action) {
            Image(systemName: role.symbolName)
                .font(.caption.weight(.semibold))
                .frame(
                    width: DesktopShellChromeMetrics.paneToggleButtonWidth,
                    height: DesktopShellChromeMetrics.paneToggleButtonHeight
                )
                .contentShape(RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.md, style: .continuous))
        }
        .buttonStyle(.plain)
        .help(label)
        .accessibilityLabel(label)

        if let shortcut {
            button.keyboardShortcut(shortcut)
        } else {
            button
        }
    }
}

struct DesktopShellTabStripView: View {
    let selectedSurface: DesktopSurface
    let selectSurface: (DesktopSurface) -> Void

    var body: some View {
        HStack(spacing: 3) {
            ForEach(DesktopSurface.allCases) { surface in
                Button {
                    selectSurface(surface)
                } label: {
                    Text(surface.rawValue)
                        .font(.caption.weight(selectedSurface == surface ? .semibold : .medium))
                        .lineLimit(1)
                        .padding(.horizontal, DesktopShellChromeMetrics.titleBarTabHorizontalPadding)
                        .padding(.vertical, DesktopShellChromeMetrics.titleBarTabVerticalPadding)
                        .background(
                            selectedSurface == surface
                            ? MelixDesignTokens.accent.opacity(MelixDesignTokens.AccentOpacity.capsule)
                            : Color.clear,
                            in: Capsule()
                        )
                }
                .buttonStyle(.plain)
                .keyboardShortcut(shortcutKey(for: surface), modifiers: .command)
                .fixedSize(horizontal: true, vertical: false)
            }
        }
        .padding(DesktopShellChromeMetrics.titleBarTabContainerInset)
        .frame(height: DesktopShellChromeMetrics.titleBarTabHeightBudget)
        .background(Color(nsColor: .windowBackgroundColor), in: Capsule())
        .overlay(
            Capsule()
                .stroke(Color.primary.opacity(MelixDesignTokens.StrokeOpacity.hairline), lineWidth: 1)
        )
    }

    private func shortcutKey(for surface: DesktopSurface) -> KeyEquivalent {
        switch surface {
        case .chat:
            return "1"
        case .image:
            return "2"
        case .server:
            return "3"
        case .tools:
            return "4"
        case .api:
            return "5"
        }
    }
}
