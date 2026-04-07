import SwiftUI

struct DesktopShellChromeView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        HStack(spacing: 16) {
            DesktopShellBrandView()

            Spacer(minLength: 12)

            DesktopShellTabStripView(
                selectedSurface: viewModel.selectedSurface,
                selectSurface: viewModel.selectSurface
            )

            Spacer(minLength: 12)

            Button(action: viewModel.openCommandCenter) {
                Image(systemName: "command.circle")
                    .font(.title3.weight(.semibold))
                    .frame(width: 30, height: 30)
                    .contentShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
            }
            .buttonStyle(.plain)
            .help("Open Command Center")
            .accessibilityLabel("Open Command Center")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(Color.primary.opacity(0.08), lineWidth: 1)
        )
    }
}

private struct DesktopShellBrandView: View {
    var body: some View {
        HStack(spacing: 10) {
            ZStack {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(Color(nsColor: .controlBackgroundColor))

                Image(nsImage: MelixBranding.workspaceLogo())
                    .resizable()
                    .interpolation(.high)
                    .scaledToFit()
                    .padding(4)
            }
            .frame(width: 28, height: 28)

            Text(MelixBranding.productName)
                .font(.headline.weight(.semibold))
                .lineLimit(1)
        }
        .fixedSize(horizontal: true, vertical: false)
    }
}

private struct DesktopShellTabStripView: View {
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
                        .padding(.horizontal, 12)
                        .padding(.vertical, 7)
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
