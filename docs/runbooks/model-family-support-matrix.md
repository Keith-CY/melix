# Model Family Support Matrix

## Purpose

This runbook explains how to inspect the repository-owned support matrix for Melix text, embedding,
and rerank families.

The matrix distinguishes two support levels:

- `contract` means the family is represented by catalog metadata and route declarations
- `live_path` means the family is backed by at least one repository integration test that exercises the real HTTP path

## Command

Render the current machine-readable matrix:

```bash
PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python python -m worker.productization.family_support_matrix
```

## Interpretation

Check the following fields for each family row:

- `capability`
- `family_id`
- `contract.route_kind`
- `contract.supported_modalities`
- `contract.supported_tasks`
- `live_path.status`
- `live_path.integration_tests`

Rows marked `contract_only` are intentional gaps. They indicate Melix can describe the family in the catalog, but repository-owned live-path verification has not landed yet.

## Operator Use

Use this matrix when:

- checking whether a requested dense or MoE text family is only declared or also live-verified
- checking whether a requested embedding or rerank family is only declared or also live-verified
- reviewing family-expansion changes for support drift
- locating the integration test that currently proves a family-specific live path

## Recovery

If the matrix drifts from runtime behavior:

1. inspect the relevant `WorkerModelCatalog` family metadata
2. re-run the linked integration test node from the matrix row
3. update the matrix builder and the linked runbook evidence in the same change
