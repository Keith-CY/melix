# Launchd Assets

This directory reserves the repository-owned location for Melix launchd startup automation.

Current workflow:

- `scripts/install_local_product.py` renders the versioned local-product launch agents into the chosen `LaunchAgents` directory.
- `scripts/uninstall_local_product.py` removes the generated launch agents and prints the matching `launchctl bootout` commands.
- `scripts/phase8_install_smoke.py` validates that the install flow can generate launchd assets, an install manifest, and a product environment file in a clean staging home directory.

Generated launch agent labels:

- `io.melix.swift-text-worker`
- `io.melix.python-worker`
- `io.melix.control-plane`
