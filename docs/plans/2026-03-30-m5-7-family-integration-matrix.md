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

## Implementation Slice

- add a repository-owned family integration matrix builder under `services/mlx-worker-python/worker/productization/`
- derive contract rows from `WorkerModelCatalog` family-specific metadata instead of duplicating supported tasks or modalities in docs
- record live-path evidence as integration test node references and operator runbook pointers
- mark families without live verification as `contract_only` so support drift stays explicit
- keep the matrix discoverable from both `docs/README.md` and `docs/runbooks/README.md`

## Measurement Points

- number of contract-supported embedding and rerank families represented in the matrix
- number of matrix rows with live-path verification evidence versus `contract_only`
- drift detection point: matrix-supported tasks and modalities must match catalog capability metadata for each family row

## Verification

- `make py-test`
- `make integration-test`

## Acceptance

- Melix has a repository-owned family support matrix tied to live verification
- support drift becomes detectable as future families are added
