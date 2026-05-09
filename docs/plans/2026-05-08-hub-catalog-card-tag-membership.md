# Hub Catalog Card Tag Membership Probe

## Goal

Reduce redundant tag materialization in Hub catalog MLX compatibility checks.

## Touched Files

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `scripts/hub_catalog_tag_normalization_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Linux Verification Path

- Focused pytest for Hub catalog behavior and the registered probe smoke test.
- Changed-scope coverage through `scripts/changed_scope_coverage.py`.
- Existing PR-scoped performance probe: `hub-catalog-tag-normalization-single-pass`.

## Probe Definition

The probe builds synthetic Hub payloads whose top-level tags are already normalized for summary fields while `cardData.tags` must still be checked for MLX compatibility. Success means the branch preserves report output and reduces `_string_list(...)` calls from card tag checks.

## Success Metrics

- Changed executable coverage for touched Python scope is at least 95%.
- `tag_normalization_calls_mean` remains one call per record on the optimized branch.
- `elapsed_ms_mean` and `peak_bytes_mean` are reported for the synthetic workload.
