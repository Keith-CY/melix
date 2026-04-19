import SwiftUI

/// Central design tokens for the Melix macOS operator app.
///
/// Mirrors `docs/design-system/colors_and_type.css`. Refer to
/// `docs/design-system/README.md` for the "Digital Broadsheet" rationale —
/// typographic structure, whitespace as hierarchy, accent as ink.
enum MelixDesignTokens {

    // MARK: - Accent

    /// Brand teal (`#0F766E`). Used for places where the Melix identity
    /// must be fixed regardless of the user's system accent (app icon,
    /// workspace badge, printed/exported artifacts).
    static let brandAccent = Color(red: 0x0F / 255.0, green: 0x76 / 255.0, blue: 0x6E / 255.0)

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
    }

    enum StrokeOpacity {
        /// Near-invisible hairline on structural containers. Aliased to
        /// `SurfaceOpacity.card` so the "6%" constant has a single source.
        static let hairline: Double = SurfaceOpacity.card
        /// Slightly stronger hairline on interactive containers — composer
        /// boxes, tab strips. Spec permits 0.06–0.08 on these surfaces.
        static let interactive: Double = 0.08
    }

    // MARK: - Status tints

    /// Base hues for chat transcript bubble backgrounds. Paired with
    /// `BubbleOpacity` to stay consistent with the `AccentOpacity` pattern.
    enum BubbleTint {
        static let user = Color.blue
        static let assistant = Color.green
        static let reasoning = Color.orange
        static let tool = Color.purple
        static let error = Color.red
    }

    /// Per-role opacities for chat bubble backgrounds. The user bubble sits
    /// slightly stronger (0.14) because blue reads softer than the warm
    /// tones on a near-white canvas; the rest match spec at 0.12.
    enum BubbleOpacity {
        static let user: Double = 0.14
        static let assistant: Double = 0.12
        static let reasoning: Double = 0.12
        static let tool: Double = 0.12
        static let error: Double = 0.12
    }

    /// Pre-composed chat bubble fills — convenience wrappers that keep
    /// callers short while exposing the underlying hue and opacity above.
    enum Bubble {
        static let user = BubbleTint.user.opacity(BubbleOpacity.user)
        static let assistant = BubbleTint.assistant.opacity(BubbleOpacity.assistant)
        static let reasoning = BubbleTint.reasoning.opacity(BubbleOpacity.reasoning)
        static let tool = BubbleTint.tool.opacity(BubbleOpacity.tool)
        static let error = BubbleTint.error.opacity(BubbleOpacity.error)
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
