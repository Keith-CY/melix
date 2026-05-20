import AppKit
import SwiftUI

private extension MelixDesignTokens.DesignColor.Components {
    func nsColor(alpha: Double) -> NSColor {
        NSColor(
            srgbRed: CGFloat(red) / 255.0,
            green: CGFloat(green) / 255.0,
            blue: CGFloat(blue) / 255.0,
            alpha: CGFloat(alpha)
        )
    }
}

private extension NSAppearance {
    var isDarkMode: Bool {
        let darkAppearances: Set<NSAppearance.Name> = [
            .darkAqua,
            .accessibilityHighContrastDarkAqua,
        ]
        let bestMatch = bestMatch(from: [
            .aqua,
            .darkAqua,
            .accessibilityHighContrastAqua,
            .accessibilityHighContrastDarkAqua,
        ])
        return bestMatch.map { darkAppearances.contains($0) } ?? false
    }
}

/// Central design tokens for the Melix macOS operator app.
///
/// Mirrors `docs/design-system/colors_and_type.css`. Refer to
/// `docs/design-system/README.md` for the "Digital Broadsheet" rationale —
/// typographic structure, whitespace as hierarchy, accent as ink.
enum MelixDesignTokens {

    struct DesignColor: Equatable {
        struct Components: Equatable {
            let red: UInt8
            let green: UInt8
            let blue: UInt8
        }

        let light: Components
        let dark: Components
        let opacity: Double

        init(red: UInt8, green: UInt8, blue: UInt8, opacity: Double = 1.0) {
            let components = Components(red: red, green: green, blue: blue)
            self.light = components
            self.dark = components
            self.opacity = opacity
        }

        init(light: Components, dark: Components, opacity: Double = 1.0) {
            self.light = light
            self.dark = dark
            self.opacity = opacity
        }

        var color: Color {
            Color(nsColor: nsColor)
        }

        var nsColor: NSColor {
            NSColor(name: nil) { appearance in
                let components = appearance.isDarkMode ? dark : light
                return components.nsColor(alpha: opacity)
            }
        }
    }

    private typealias Components = DesignColor.Components

    enum Palette {
        static let accent = DesignColor(red: 0x0F, green: 0x76, blue: 0x6E)

        static let foregroundPrimary = DesignColor(
            light: Components(red: 0x0A, green: 0x0A, blue: 0x0A),
            dark: Components(red: 0xFD, green: 0xFD, blue: 0xFD)
        )
        static let foregroundSecondary = DesignColor(
            light: Components(red: 0x3A, green: 0x3A, blue: 0x3A),
            dark: Components(red: 0xC8, green: 0xC8, blue: 0xC8)
        )
        static let foregroundTertiary = DesignColor(
            light: Components(red: 0x6B, green: 0x6B, blue: 0x6B),
            dark: Components(red: 0x8A, green: 0x8A, blue: 0x8A)
        )
        static let foregroundQuaternary = DesignColor(
            light: Components(red: 0x9A, green: 0x9A, blue: 0x9A),
            dark: Components(red: 0x5A, green: 0x5A, blue: 0x5A)
        )
        static let foregroundInverse = DesignColor(
            light: Components(red: 0xFD, green: 0xFD, blue: 0xFD),
            dark: Components(red: 0x0A, green: 0x0A, blue: 0x0A)
        )

        static let backgroundBase = DesignColor(
            light: Components(red: 0xFA, green: 0xFA, blue: 0xFA),
            dark: Components(red: 0x1A, green: 0x1A, blue: 0x1A)
        )
        static let backgroundSurface = DesignColor(
            light: Components(red: 0xFF, green: 0xFF, blue: 0xFF),
            dark: Components(red: 0x22, green: 0x22, blue: 0x22)
        )
        static let backgroundElevated = DesignColor(
            light: Components(red: 0xF5, green: 0xF5, blue: 0xF5),
            dark: Components(red: 0x2A, green: 0x2A, blue: 0x2A)
        )
        static let backgroundSunken = DesignColor(
            light: Components(red: 0xF0, green: 0xF0, blue: 0xF0),
            dark: Components(red: 0x16, green: 0x16, blue: 0x16)
        )

        static let success = DesignColor(red: 0x14, green: 0xA0, blue: 0x5A)
        static let warning = DesignColor(red: 0xD9, green: 0x77, blue: 0x06)
        static let error = DesignColor(red: 0xDC, green: 0x26, blue: 0x26)

        static let userBubble = DesignColor(red: 0x00, green: 0x64, blue: 0xDC)
        static let assistantBubble = DesignColor(red: 0x14, green: 0xA0, blue: 0x50)
        static let reasoningBubble = DesignColor(red: 0xDC, green: 0x6E, blue: 0x14)
        static let toolBubble = DesignColor(red: 0x78, green: 0x3C, blue: 0xC8)
        static let errorBubble = DesignColor(red: 0xD2, green: 0x28, blue: 0x28)
    }

    // MARK: - Accent

    /// Brand teal (`#0F766E`). Kept separate from `accent` so identity marks
    /// and interactive affordances remain semantically distinct, even though
    /// the design system intentionally maps both to CSS `--accent`.
    static let brandAccent = Palette.accent.color

    /// Design-system accent. Use for interaction signals: links, focus,
    /// selection, active tabs, and one primary CTA per screen.
    static let accent = Palette.accent.color

    enum AccentOpacity {
        /// Medium accent wash (`--accent-medium` = 32%).
        static let medium: Double = 0.32
        /// Selected row / bubble background (`--accent-weak` ≈ 12%).
        static let weak: Double = 0.12
        /// Selection emphasis for rows, chips, and primary pills.
        static let selected: Double = weak
        /// Capsule tab active fill.
        static let capsule: Double = weak
        /// Hover hint for interactive surfaces.
        static let faint: Double = 0.06
    }

    // MARK: - Surfaces

    enum SurfaceOpacity {
        /// Card / tile fill when painting `Color.secondary` — near-invisible wash.
        static let card: Double = 0.06
        /// Slightly more present tile fill (nested cards, secondary surfaces).
        static let elevated: Double = 0.08
        /// Standard card fill when painting `.quaternary` — see `melixCard()`.
        static let quaternaryCard: Double = 0.6
    }

    enum StrokeOpacity {
        /// Near-invisible hairline on structural containers. Aliased to
        /// `SurfaceOpacity.card` so the "6%" constant has a single source.
        static let hairline: Double = SurfaceOpacity.card
        /// Slightly stronger hairline on interactive containers — composer
        /// boxes, tab strips. Spec permits 0.06–0.08 on these surfaces.
        static let interactive: Double = 0.08
        /// Visible enough for dense forms where fields must not disappear into
        /// surrounding card surfaces.
        static let input: Double = 0.18
        /// Focus ring for text entry and repeated operator configuration flows.
        static let focusedInput: Double = 0.72
    }

    // MARK: - Status tints

    enum StatusColor {
        static let success = Palette.success.color
        static let warning = Palette.warning.color
        static let error = Palette.error.color
        /// CSS `--color-info` intentionally aliases `--accent`; informational
        /// notices use ink color rather than introducing a separate blue.
        static let info = accent
    }

    enum StateOpacity {
        /// Non-chat status background tint for rows and job states.
        static let background: Double = 0.09
    }

    /// Base hues for chat transcript bubble backgrounds. Paired with
    /// `BubbleOpacity` to stay consistent with the `AccentOpacity` pattern.
    /// These are intentionally flat `Color` values; transcript bubbles do not
    /// use gradients or materials in the Digital Broadsheet system.
    enum BubbleTint {
        static let user = Palette.userBubble.color
        static let assistant = Palette.assistantBubble.color
        static let reasoning = Palette.reasoningBubble.color
        static let tool = Palette.toolBubble.color
        static let error = Palette.errorBubble.color
    }

    /// Per-role opacities for chat bubble backgrounds, matching
    /// `docs/design-system/colors_and_type.css`.
    enum BubbleOpacity {
        static let user: Double = 0.10
        static let assistant: Double = 0.09
        static let reasoning: Double = 0.09
        static let tool: Double = 0.09
        static let error: Double = 0.09
    }

    // MARK: - Corner radii

    enum Radius {
        /// Tags, small badges.
        static let sm: CGFloat = 6
        /// Buttons, icon button hit areas.
        static let md: CGFloat = 8
        /// Composer, session rows, input fields.
        static let lg: CGFloat = 10
        /// Dashboard cards, chat bubbles.
        static let xl: CGFloat = 12
    }

    // MARK: - Spacing (4px base)

    enum Spacing {
        static let xs: CGFloat = 4
        static let sm: CGFloat = 8
        static let md: CGFloat = 12
        /// Sanctioned half-step between `md` and `lg` for panel insets
        /// where 12 reads tight and 16 reads loose. Documented exception
        /// to the 4px base unit — see `docs/design-system/README.md`.
        static let panelInset: CGFloat = 14
        static let lg: CGFloat = 16
        static let xl: CGFloat = 20
        static let xxl: CGFloat = 24
        static let huge: CGFloat = 32
    }

    enum ControlMetrics {
        /// Shared height for operator text fields and inline actions in dense
        /// configuration rows.
        static let operatorFieldHeight: CGFloat = 36
    }

    // MARK: - Typography

    /// Mirrors SwiftUI semantic text styles. Prefer these when composing
    /// views so the type scale stays consistent with the design brief.
    enum Typography {
        static let largeTitle = Font.largeTitle.weight(.bold)
        static let title1 = Font.title.weight(.semibold)
        static let title2 = Font.title2.weight(.semibold)
        static let title3 = Font.title3.weight(.semibold)
        static let headline = Font.headline
        static let body = Font.body
        static let callout = Font.callout
        static let caption = Font.caption
        static let caption2 = Font.caption2

        /// Monospaced variants for code, CLI output, request IDs, metrics.
        /// Use `.monospacedDigit()` on number-heavy labels for tabular alignment.
        static let mono = Font.system(.body, design: .monospaced)
        static let monoCaption = Font.system(.caption, design: .monospaced)
        static let monoCaption2 = Font.system(.caption2, design: .monospaced)
    }
}

// MARK: - Convenience modifiers

extension View {
    /// Apply the standard Melix card surface: quaternary-tinted rounded
    /// rectangle with the XL radius. No border, no shadow — whitespace is
    /// hierarchy.
    func melixCard(radius: CGFloat = MelixDesignTokens.Radius.xl) -> some View {
        background(
            .quaternary.opacity(MelixDesignTokens.SurfaceOpacity.quaternaryCard),
            in: RoundedRectangle(cornerRadius: radius, style: .continuous)
        )
    }

    /// Apply the standard selected-row accent fill.
    ///
    /// The unselected branch paints a near-invisible secondary wash (6%)
    /// so rows read as tiles even when inactive — matches the session-row
    /// treatment in the design mock (`ChatView.jsx`: `rgba(0,0,0,0.03)`).
    /// Pass `unselectedFill: .clear` for contexts where the tile fill
    /// would double-up with an outer surface.
    func melixSelection(
        _ isSelected: Bool,
        radius: CGFloat = MelixDesignTokens.Radius.lg,
        unselectedFill: Color = Color.secondary.opacity(MelixDesignTokens.SurfaceOpacity.card)
    ) -> some View {
        background(
            isSelected
                ? MelixDesignTokens.accent.opacity(MelixDesignTokens.AccentOpacity.selected)
                : unselectedFill,
            in: RoundedRectangle(cornerRadius: radius, style: .continuous)
        )
    }

    /// Render text as a section microhead: 10pt, semibold, tertiary,
    /// uppercase with tight tracking. The "Digital Broadsheet" pattern for
    /// GroupBox-style labels ("SESSION", "CHAT SESSIONS", etc.).
    func melixSectionLabel() -> some View {
        self
            .font(.system(size: 10, weight: .semibold))
            .foregroundStyle(.tertiary)
            .textCase(.uppercase)
            .tracking(0.6)
    }
}

struct MelixOperatorTextFieldModifier: ViewModifier {
    @FocusState private var isFocused: Bool

    func body(content: Content) -> some View {
        content
            .textFieldStyle(.plain)
            .font(MelixDesignTokens.Typography.body)
            .padding(.horizontal, MelixDesignTokens.Spacing.md)
            .padding(.vertical, MelixDesignTokens.Spacing.sm)
            .frame(minHeight: MelixDesignTokens.ControlMetrics.operatorFieldHeight)
            .background(
                RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.md, style: .continuous)
                    .fill(MelixDesignTokens.Palette.backgroundSurface.color)
            )
            .overlay(
                RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.md, style: .continuous)
                    .stroke(
                        isFocused
                            ? MelixDesignTokens.accent.opacity(MelixDesignTokens.StrokeOpacity.focusedInput)
                            : Color.primary.opacity(MelixDesignTokens.StrokeOpacity.input),
                        lineWidth: isFocused ? 1.5 : 1
                    )
            )
            .focused($isFocused)
    }
}

extension View {
    func melixOperatorTextFieldStyle() -> some View {
        modifier(MelixOperatorTextFieldModifier())
    }
}

/// Card container with a microhead section label. Replaces SwiftUI's
/// default `GroupBox` for inspector/sidebar sections where the spec calls
/// for the "Digital Broadsheet" header treatment.
struct MelixSectionCard<Content: View>: View {
    let title: String
    @ViewBuilder let content: () -> Content

    init(_ title: String, @ViewBuilder content: @escaping () -> Content) {
        self.title = title
        self.content = content
    }

    var body: some View {
        VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.sm) {
            Text(title).melixSectionLabel()
            content()
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(MelixDesignTokens.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .melixCard()
    }
}

struct MelixActionableEmptyState<Actions: View>: View {
    let title: String
    let systemImage: String
    let detail: String
    @ViewBuilder let actions: () -> Actions

    var body: some View {
        VStack(spacing: MelixDesignTokens.Spacing.md) {
            Image(systemName: systemImage)
                .font(.system(size: 28, weight: .medium))
                .foregroundStyle(MelixDesignTokens.accent)
                .frame(width: 46, height: 46)
                .background(
                    MelixDesignTokens.accent.opacity(MelixDesignTokens.AccentOpacity.weak),
                    in: RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.xl, style: .continuous)
                )

            VStack(spacing: MelixDesignTokens.Spacing.xs) {
                Text(title)
                    .font(MelixDesignTokens.Typography.headline)
                Text(detail)
                    .font(MelixDesignTokens.Typography.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .lineLimit(3)
            }

            actions()
                .controlSize(.small)
        }
        .padding(MelixDesignTokens.Spacing.xl)
        .frame(maxWidth: .infinity, minHeight: 180)
        .background(
            MelixDesignTokens.Palette.backgroundSurface.color,
            in: RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.xl, style: .continuous)
        )
        .overlay(
            RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.xl, style: .continuous)
                .stroke(Color.primary.opacity(MelixDesignTokens.StrokeOpacity.hairline), lineWidth: 1)
        )
    }
}
