# Packaging Structure

This directory owns the repository-level packaging contract for Melix Apple Silicon delivery
targets.

The current target matrix is:

- `launch_agents_checkout`
- `homebrew_service`
- `macos_app_bundle_preview`

Each target keeps the same logical product identity (`io.melix`) and shared runtime semantics while
making these target-specific fields explicit in generated metadata:

- `packaging_target_id`
- `packaging_kind`
- `distribution_channel`
- `runtime_layout`
- `state_contract`
- `update_strategy`

Current repository-owned assets in this area:

- update-channel metadata under `update-channels/`
- launch-agent install manifests and environment exports
- Homebrew formula and service assets under `../homebrew/`
- macOS app-bundle packaging metadata embedded by `scripts/package_macos_menubar_app.py`

Use `docs/runbooks/platform-packaging-targets.md` for the canonical operator and release-facing
target matrix, and `scripts/m8_packaging_target_smoke.py --json` to validate the generated target
metadata across all supported packaging outputs.
