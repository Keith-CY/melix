---
name: melix-design
description: Use this skill to generate well-branded interfaces and assets for Melix, the local-first AI runtime for Apple Silicon (MLX, LoRA training, benchmarking). Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping the macOS operator app and CLI tooling surfaces.
user-invocable: true
---

Read the README.md file within this skill, and explore the other available files.

If creating visual artifacts (slides, mocks, throwaway prototypes, etc), copy assets out and create static HTML files for the user to view. If working on production code, you can copy assets and read the rules here to become an expert in designing with this brand.

Key files to read first:
- `README.md` — product context, visual foundations, content guidelines, iconography
- `colors_and_type.css` — all CSS custom properties (colors, type, spacing, radii)
- `ui_kits/macos-app/index.html` — full interactive prototype of the macOS operator UI
- `assets/melix_logo.svg` — primary logo

Core design principles:
- "The Digital Broadsheet" — typographic structure, whitespace as hierarchy
- Accent as Ink: teal #0F766E used only for interaction signals (links, focus, selection, one CTA per screen)
- No borders ever (only near-invisible 0.06 opacity hints on interactive containers)
- Maximum whitespace — always err toward more, never less
- System-ui / SF Pro typography; JetBrains Mono / SF Mono for code/metrics
- No illustrations, no gradients, no textures — pure type and whitespace

If the user invokes this skill without any other guidance, ask them what they want to build or design, ask some questions, and act as an expert designer who outputs HTML artifacts _or_ production code, depending on the need.
