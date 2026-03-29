# Release Gates

This directory stores versioned release-gate policy and workflow assets for Melix.

Current assets:

- `phase8-release-gate-policy.json`: deterministic release thresholds for install, benchmark, recovery, and training evidence

Release gate automation is driven by:

- `scripts/phase8_release_gate.py`
- `.github/workflows/release-gates.yml`
- `docs/runbooks/phase-8-release-gates.md`
