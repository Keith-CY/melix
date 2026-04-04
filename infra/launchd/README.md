# Launchd Assets

This directory owns the repository-facing launchd automation contract for the
`launch_agents_checkout` packaging target.

Current workflow:

- `scripts/install_local_product.py` renders the versioned local-product launch agents into the chosen `LaunchAgents` directory.
- `scripts/uninstall_local_product.py` removes the generated launch agents and prints the matching `launchctl bootout` commands.
- `scripts/phase8_install_smoke.py` validates that the install flow can generate launchd assets, an install manifest, and a product environment file in a clean staging home directory.

Generated launch agent labels:

- `io.melix.swift-text-worker`
- `io.melix.python-worker`
- `io.melix.control-plane`

Generated install artifacts for this target share the logical product identity `io.melix` and add
explicit packaging metadata in the install manifest and environment export:

- `packaging_target_id = launch_agents_checkout`
- `packaging_kind = launch_agents`
- `distribution_channel = local_checkout`
- `state_contract = install_manifest_v1`
