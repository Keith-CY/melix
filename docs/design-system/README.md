# Melix Design System

**Melix** is a local-first AI runtime for Apple Silicon — a single product surface that unifies model serving, LoRA fine-tuning, benchmarking, evaluation, and CLI tooling on one machine.

## Sources

| Resource | Path / URL |
|---|---|
| Logo SVG | `assets/melix_logo.svg` |
| macOS app codebase | `github.com/Keith-CY/melix` (branch `main`) |
| Design brief | Provided inline (see Visual Foundations) |

The app is a Swift/SwiftUI macOS menubar operator. No web frontend exists; this design system translates the SwiftUI patterns to web-compatible CSS/HTML for prototyping and documentation.

---

## Products

| Surface | Description |
|---|---|
| **macOS Operator App** | Native menubar app. Five tabs: Chat, Image, Server, Tools, API. |
| **`melix` CLI** | Shell-level interface for all runtime operations. |
| **Local runtime** | Swift control plane + Python worker (not a UI surface). |

The design system covers the **macOS operator app** UI kit.

---

## Content Fundamentals

### Voice & Tone
- **Sparse, precise, technical.** Copy reads like terminal output formatted for a human.
- **Lowercase-leaning** in labels and captions. Proper nouns (Melix, LoRA, MLX, Hugging Face) are always capitalized correctly.
- **No marketing fluff.** Labels say exactly what they do: "Train LoRA", "Bench", "Activate Adapter".
- **No emojis.** None in the UI, none in copy.
- **First person: implicit.** The app acts on behalf of the user — no "you" or "I".
- **Status text is past-tense verb + noun**: "smoke validation passed", "no training jobs recorded yet", "request aborted".
- **Numbers as data**: monospaced, tabular, right-aligned where possible.
- **Errors are factual**: no apology, no softening. "Server session unavailable." not "Oops!"

### Casing
- **Title Case** for tab labels, section headers, button labels.
- **Sentence case** for descriptions, status text, inline notices.
- **ALL CAPS** never used in the UI.

### Examples
> `No Chat Sessions` — section empty state headline  
> `Create a new chat after starting a Server Session.` — description  
> `queued 2  active 1  bp 0.14` — scheduler lane status  
> `smoke validation passed` — operation status  
> `Train LoRA` — action button  

---

## Visual Foundations

### Creative North Star: "The Digital Broadsheet"
Typography is structure. Whitespace is hierarchy. Color is ink — reserved only for interaction signals.

### Colors
- **Background**: Near-white `#FAFAFA` (light) / near-black `#1A1A1A` (dark). System macOS window background.
- **Accent (Ink)**: Teal `#0F766E` — mirrors the macOS system accent color used throughout the SwiftUI app. Used *only* for links, focus rings, selection, active tabs, and one primary CTA per screen.
- **Foreground**: `#0A0A0A` primary, stepping down through `#3A3A3A → #6B6B6B → #9A9A9A`.
- **Status tints**: Blue (user), Green (assistant), Orange (reasoning), Purple (tool), Red (error) — all at ~10–14% opacity.
- **No structural color.** Sections are separated by whitespace and typographic hierarchy, not colored bands.

### Typography
- **Font**: `system-ui` / SF Pro (macOS native). Web fallback: Inter.
- **Monospace**: SF Mono / JetBrains Mono — used for code, CLI output, request IDs, metrics.
- **Scale**: SwiftUI semantic scale: Large Title (28px bold) → Title 2 (18px semibold) → Headline (13px semibold) → Body (13px) → Caption (11px) → Caption 2 (10px).
- **Letter-spacing**: Negative on display sizes (−0.015em to −0.02em). Normal on body.
- **No decorative or editorial typefaces.** Pure system type.

### Spacing
- **Base unit: 4px.** All spacing is multiples: 4, 8, 12, 14, 16, 20, 24.
- **Generous internal padding**: panels use 14–20px insets.
- **Row spacing**: 6–12px between list items.
- **Maximum whitespace**: always err toward more space, not less.

### Borders
- **No structural borders. Ever.** Sections are divided by whitespace.
- The only permitted strokes: `rgba(0,0,0,0.06–0.08)` on interactive containers (tab strips, composer boxes) — near-invisible.
- Active input: bottom border only (`1px solid #0A0A0A`).
- Focus ring: `1px solid var(--accent)`, offset 2px.

### Corner Radii
| Token | Value | Usage |
|---|---|---|
| `--radius-sm` | 6px | Tags, small badges |
| `--radius-md` | 8px | Buttons, icon button hit areas |
| `--radius-lg` | 10px | Composer, session rows, input fields |
| `--radius-xl` | 12px | Dashboard cards, chat bubbles |
| `--radius-full` | 9999px | Tab strip capsule, status pills |

### Backgrounds
- **No images**, no full-bleed photography, no gradients.
- **No textures or patterns.**
- Card/tile: `.quaternary.opacity(0.6)` ≈ `rgba(0,0,0,0.04)` fill. No shadow, no border.
- Selected row: `var(--accent-weak)` = teal at 12% opacity.

### Animation
- **Minimal.** SwiftUI default spring transitions. No custom bounce or elaborate sequences.
- State changes: immediate or with a subtle `0.15s ease` opacity fade.
- No loading spinners with custom animations; use system progress indicators.

### Hover / Press States
- Hover: subtle background tint (`var(--accent-faint)` or neutral `rgba(0,0,0,0.04)`).
- Press: slight darken on primary button; no scale transform.
- Plain icon buttons: opacity 0.6 on hover.

### Icons
- **SF Symbols exclusively** in the macOS app. See ICONOGRAPHY section.
- No custom icon illustrations.
- No emoji as icons.

### Cards
- `RoundedRectangle(cornerRadius: 12)` with `.quaternary.opacity(0.6)` fill.
- No box-shadow. No border.
- Internal padding: 12–16px.

### Elevation / Shadow
- No decorative shadows on cards or panels.
- Floating overlays (popovers, command center): `0 8px 32px rgba(0,0,0,0.14)`.

### Imagery
- **None.** The product is purely data/text-driven.
- No illustrations, no stock photos.

---

## Iconography

**Production app**: SF Symbols (Apple's system icon font). No custom SVGs, no icon fonts, no PNGs.

Key symbols in use:
| Symbol | `systemName` | Usage |
|---|---|---|
| Sidebar | `sidebar.left` / `sidebar.right` | Pane toggles |
| Command | `command.circle` | Command center CTA |
| Plus | `plus` | New chat session |
| Ellipsis menu | `ellipsis.circle` | Session row actions |
| Checkmark | `checkmark.circle.fill` | Capability ready |
| Dotted circle | `circle.dotted` | Capability not ready |
| Chevron | `chevron.down` | Menu indicator |

**Web prototypes**: Use [Lucide Icons](https://lucide.dev) (CDN: `https://unpkg.com/lucide@latest`) as the nearest stroke-weight equivalent to SF Symbols.

Substitution flag: Lucide icons are used as SF Symbol stand-ins in web prototypes. Do not ship Lucide to production.

---

## File Index

```
/
├── README.md                  ← This file
├── colors_and_type.css        ← CSS variables: colors, type, spacing, radii
├── SKILL.md                   ← Agent skill entrypoint
├── assets/
│   └── melix_logo.svg         ← Primary wordmark / app icon SVG
├── preview/                   ← Design System tab cards
│   ├── colors-base.html
│   ├── colors-accent.html
│   ├── colors-semantic.html
│   ├── type-scale.html
│   ├── type-mono.html
│   ├── spacing-tokens.html
│   ├── radius-tokens.html
│   ├── btn-primary.html
│   ├── btn-variants.html
│   ├── input-states.html
│   ├── chat-bubbles.html
│   ├── tab-strip.html
│   ├── card-tile.html
│   └── logo.html
└── ui_kits/
    └── macos-app/
        ├── README.md
        ├── index.html          ← Full app prototype (Chat tab)
        ├── Tokens.jsx
        ├── Shell.jsx
        ├── ChatView.jsx
        ├── ServerView.jsx
        └── ToolsView.jsx
```
