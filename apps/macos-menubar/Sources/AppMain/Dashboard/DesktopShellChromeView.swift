import SwiftUI

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
    let openCommandCenter: () -> Void

    var body: some View {
        Button(action: openCommandCenter) {
            Image(systemName: "command.circle")
                .font(.title3.weight(.semibold))
                .frame(width: 28, height: 28)
                .contentShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        }
        .buttonStyle(.plain)
        .help("Open Command Center")
        .accessibilityLabel("Open Command Center")
        .fixedSize(horizontal: true, vertical: false)
    }
}

struct DesktopShellTabStripView: View {
    let selectedSurface: DesktopSurface
    let selectSurface: (DesktopSurface) -> Void

    var body: some View {
        HStack(spacing: 4) {
            ForEach(DesktopSurface.allCases) { surface in
                Button {
                    selectSurface(surface)
                } label: {
                    Text(surface.rawValue)
                        .font(.subheadline.weight(selectedSurface == surface ? .semibold : .medium))
                        .lineLimit(1)
                        .padding(.horizontal, 11)
                        .padding(.vertical, 6)
                        .background(
                            selectedSurface == surface
                            ? Color.accentColor.opacity(0.18)
                            : Color.clear,
                            in: Capsule()
                        )
                }
                .buttonStyle(.plain)
                .fixedSize(horizontal: true, vertical: false)
            }
        }
        .padding(4)
        .background(Color(nsColor: .windowBackgroundColor), in: Capsule())
        .overlay(
            Capsule()
                .stroke(Color.primary.opacity(0.06), lineWidth: 1)
        )
    }
}
