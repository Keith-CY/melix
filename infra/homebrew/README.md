# Homebrew Assets

This directory contains the repository-owned Homebrew distribution assets for Melix.

Current workflow:

- `infra/homebrew/Formula/melix.rb` installs Melix directly from the checked-out repository root so the formula stays aligned with the local product source tree before release archives are introduced.
- `scripts/melix_homebrew_service.py manifest --json` renders the repository-owned Homebrew service manifest without starting any processes.
- `scripts/m8_homebrew_formula_smoke.py` validates that the checked-in formula matches the canonical renderer and still advertises Homebrew service support.
- `scripts/m8_homebrew_service_smoke.py` validates that the Homebrew service supervisor can start and stop the Melix three-process bundle deterministically.

Installed command surface:

- `melix`
- `melix-control-plane`
- `melix-text-worker-swift`
- `melix-homebrew-service`
