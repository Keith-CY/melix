# Packaging Structure

This directory reserves the repository-owned location for future Melix packaging assets.

Phase 8 milestone `P8-M4` establishes:

- local product install and uninstall scripts
- launchd startup automation assets
- a reproducible install manifest for local product flows
- repository-owned update-channel metadata under `update-channels/`

The local-product packaging flow now treats the generated install manifest as the authoritative
operator-visible record for:

- selected Melix product version
- update-channel path
- requested and selected HTTP ports
- ready-probe URL
- control-plane and worker log paths used by startup diagnostics

Future work can add:

- Homebrew formula and service assets under `../homebrew/`
- signed application bundles
- installer packaging assets
- archive composition and notarization helpers
