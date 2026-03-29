# M5.7 Family Integration Matrix

## Goal

Close the embedding, rerank, and family-expansion milestone with a repository-owned matrix of supported families, tasks, modalities, and verification evidence.

## Scope

- add a family support matrix
- connect support declarations to integration tests and operator-facing diagnostics
- keep the matrix discoverable from roadmap and operator docs

## Files

- update `docs/README.md`
- update `docs/runbooks/`
- update `tests/integration/`
- update `services/mlx-worker-python/worker/productization/`

## Implementation Notes

- the matrix should distinguish contract support from live-path support
- support declarations should match registry metadata and integration evidence
- keep the matrix machine-readable where practical

## Verification

- `make py-test`
- `make integration-test`

## Acceptance

- Melix has a repository-owned family support matrix tied to live verification
- support drift becomes detectable as future families are added
