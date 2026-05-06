# Hub Catalog Empty Card Tags Fast Path

## Goal

Avoid redundant fallback tag normalization in the Hub catalog compatibility check when a model payload has already missed the top-level MLX signals and `cardData.tags` is absent or empty.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python` and is verified locally on Linux with focused pytest, changed-scope coverage, and the existing PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `scripts/hub_catalog_tag_normalization_probe.py`
- `docs/plans/2026-05-06-hub-catalog-empty-card-tags-fast-path.md`

## Performance probe

Registered probe: `hub-catalog-tag-normalization-single-pass`.

The probe measures synthetic Hub summary-record construction for model payloads that have top-level tags but no MLX compatibility signal and no `cardData.tags`. The success signal is lower `tag_normalization_calls_mean` while preserving record counts and local-fit/quantization output.

## Success metrics

- Focused tests pass.
- Changed-scope coverage is at least 95% for touched executable Python lines.
- Local base-vs-head probe shows fewer tag-normalization helper calls with no behavior drift.
