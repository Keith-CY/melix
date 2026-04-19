import SwiftUI

/// Central design tokens for the Melix macOS operator app.
///
/// Mirrors `docs/design-system/colors_and_type.css`. Refer to
/// `docs/design-system/README.md` for the "Digital Broadsheet" rationale —
/// typographic structure, whitespace as hierarchy, accent as ink.
enum MelixDesignTokens {

    // MARK: - Accent

    /// Brand teal. Used for places where the Melix identity must be fixed
    /// regardless of the user's system accent (app icon, workspace badge,
    /// printed/exported artifacts).
    static let brandAccent = Color(red: 0x0F / 255, green: 0x76 / 255, blue: 0x6E / 255)

    /// System accent. Prefer this for interaction signals (focus, selection,
    /// active tab, one primary CTA per screen) so macOS users' accent
    /// customization is honored.
    static let accent = Color.accentColor

    enum AccentOpacity {
        /// Selected row / bubble background (`--accent-weak` ≈ 12%).
        static let weak: Double = 0.12
        /// Selection emphasis for chips and primary pills.
        static let selected: Double = 0.14
        /// Capsule tab active fill.
        static let capsule: Double = 0.18
        /// Stroke / border accent (focus ring, emphasis outline).
        static let stroke: Double = 0.22
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
        /// Hairline divider or near-invisible outline on interactive containers.
        static let hairline: Double = 0.06
    }

    // MARK: - Status tints

    /// Chat transcript bubble tints. Keep opacities low (≈ 10–14%) so the
    /// bubble reads as ink-on-paper rather than a colored card.
    enum Bubble {
        static let user = Color.blue.opacity(0.14)
        static let assistant = Color.green.opacity(0.12)
        static let reasoning = Color.orange.opacity(0.12)
        static let tool = Color.purple.opacity(0.12)
        static let error = Color.red.opacity(0.12)
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
        static let lg: CGFloat = 16
        static let xl: CGFloat = 20
        static let xxl: CGFloat = 24
        static let huge: CGFloat = 32
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
    func melixSelection(_ isSelected: Bool, radius: CGFloat = MelixDesignTokens.Radius.lg) -> some View {
        background(
            isSelected
                ? MelixDesignTokens.accent.opacity(MelixDesignTokens.AccentOpacity.selected)
                : Color.secondary.opacity(MelixDesignTokens.SurfaceOpacity.card),
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
