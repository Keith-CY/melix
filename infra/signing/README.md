# Signing Structure

This directory reserves the repository-owned location for Melix signing and notarization material
for the app-bundle packaging targets.

Current guidance:

- signing must not introduce a second logical product identity outside the shared `io.melix`
  packaging target contract
- signing and notarization attach to bundle-oriented targets such as
  `macos_app_bundle_preview` and future release bundle variants
- signing metadata should refine the distribution path only; it must not fork runtime semantics,
  update metadata, or operator-facing product naming
