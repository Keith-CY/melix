# Hub Catalog Quantization Tag Membership Fast Path

## Goal

Reduce repeated Hub catalog summary-record overhead for common exact quantization byte-width tags without changing quantization priority or summary text.

## Registered probe

The affected path is covered by the registered PR-scoped probe `hub-catalog-tag-normalization-single-pass` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_tag_normalization_probe.py`

## Slice

This Python-only Linux-verifiable slice narrows byte-width detection in `hub_catalog.py`:

- Keep exact lowercase byte-width tags on direct set-membership checks before scanning tag substrings.
- Preserve substring fallback for non-standard byte-width aliases.
- Preserve bytes-per-parameter priority (`2-bit`, `3-bit`, `4-bit`, `8-bit`, `fp32`).

## Verification

Run the registered focused test command, changed-scope coverage command, and local registered probe against an `origin/main` baseline worktree and this branch. CI PR-scoped performance remains the merge gate before squash merge.
