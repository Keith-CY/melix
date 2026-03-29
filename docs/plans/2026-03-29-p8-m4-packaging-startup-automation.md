# P8-M4 Packaging and Startup Automation

## Goal

Make Melix installable as a reproducible local product layout with launchd startup assets, installer and uninstall scripts, and a machine-checkable install smoke path.

## Scope

- add a repository-owned local-product install layout model
- render launchd assets for the Swift text worker, Python compatibility worker, and Swift control plane
- add install and uninstall scripts for local operator use
- add an install smoke script with measurable install-render metrics
- document the local product install flow and infra layout

## Files

- create `services/mlx-worker-python/worker/productization/*`
- create `services/mlx-worker-python/tests/test_install_assets.py`
- create `scripts/install_local_product.py`
- create `scripts/uninstall_local_product.py`
- create `scripts/phase8_install_smoke.py`
- create `infra/launchd/README.md`
- create `infra/packaging/README.md`
- create `infra/signing/README.md`
- create `docs/runbooks/phase-8-local-install.md`
- update `Makefile`
- update `README.md`
- update `docs/README.md`
- update `docs/runbooks/README.md`

## Implementation Notes

- keep the install flow local-first and deterministic by default
- treat launchd assets as generated product artifacts owned by repository code
- avoid hard-coding user-specific home paths in committed assets
- make install output machine-readable through a JSON install manifest
- define bootstrap and bootout commands even when tests do not execute `launchctl`

## Verification

- `make py-test`
- `python3 scripts/phase8_install_smoke.py --json`
- `git diff --check`

## Acceptance

- a clean staging home directory can receive launchd assets, an environment file, and an install manifest through scripted steps
- the generated manifest includes bootstrap and bootout commands for all three local product services
- install automation stays reproducible without depending on manual path edits
