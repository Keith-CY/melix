# Issue 1453 Batched Quantized KV Masks Plan

## Source

- Issue: `#1453` / Unit 2.3.1 from `#1431`
- Governing plan: `docs/plans/2026-04-26-issue-42-multimodal-fast-paths.md`

## Scope

Add a focused diagnostics receipt for batched quantized KV cache mask fixtures
with unequal per-row offsets. This slice proves the geometry and parity
contracts used by the multimodal fast-path plan without changing native decode
kernels, public protocol schemas, or runtime admission decisions.

## Design

- Add a `build_quantized_kv_mask_receipt` helper beside the existing
  multimodal position receipt builders.
- Record each batch row's cache offset, query length, key/value length, expected
  cache-mask shape, observed cache-mask shape, and drift reasons.
- Record the full list of per-row offsets and whether the fixture exercises
  unequal offsets.
- Record quantized-vs-unquantized logit parity as a deterministic numeric
  receipt with maximum absolute delta and tolerance.
- Keep the receipt JSON-serializable and independent of MLX array imports so it
  can be used by deterministic fixtures and diagnostics probes.

## Performance Probes

This issue adds diagnostics and fixture coverage only. The success probes are:

- receipt construction remains pure Python and O(batch rows + logits compared);
- focused Python tests verify unequal-offset geometry and logit parity;
- the pre-commit performance report must not show an in-scope regression.

## Verification

- Run the focused multimodal fast-path pytest target.
- Run coverage for the changed receipt module and related fast-path tests.
- Run the repository pre-commit hook before committing so the full local test
  gate and scoped performance report execute on the task branch.
