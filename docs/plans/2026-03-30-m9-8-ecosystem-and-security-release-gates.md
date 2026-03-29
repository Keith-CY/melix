# M9.8 Ecosystem And Security Release Gates

## Goal

Extend release-gate automation so ecosystem integration, security closure, and stability evidence become formal release requirements.

## Scope

- add ecosystem and security gate inputs
- preserve machine-readable gate output
- keep policy versioned in the repository

## Files

- update `services/mlx-worker-python/worker/productization/release_gates.py`
- update `infra/release/`
- update `scripts/`
- update `docs/runbooks/`

## Implementation Notes

- gate inputs should come from repository-owned evidence, not undocumented external checks
- policy should distinguish hard blockers from informational warnings where necessary
- keep ecosystem and security signals visible in release reports

## Verification

- touched-scope release-gate command for ecosystem and security signals
- `make py-test`

## Acceptance

- release automation can fail closed on missing ecosystem or security evidence
- gate outputs remain machine-readable and versioned in the repository
