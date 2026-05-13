# Hub Catalog Quantization Tag Fast Paths

## Scope

This Python-only performance slice is limited to Hub catalog local-fit quantization tag classification in `services/mlx-worker-python/worker/model_ops/hub_catalog.py`.

## Registered Probe

The affected path is covered by the existing PR-scoped performance probe `hub-catalog-tag-normalization-single-pass` in `infra/perf/pr_scoped_probes.json`. The registered probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for Hub catalog behavior tests, changed-scope coverage, and the synthetic Hub catalog tag/local-fit workload.

## Optimization

Replace `_bytes_per_parameter(...)` temporary joined lowered-tag string allocation with a single scan over the lowered tag set, and replace `_quantization_summary(...)` alias-set intersections with direct membership checks. Both changes preserve the existing quantization priority and summary order while reducing per-record temporary allocations in local-fit estimates.

## Verification Plan

- Run focused Hub catalog tests from the registered probe.
- Run changed-scope coverage from the registered probe.
- Run the registered local probe on Linux with an `origin/main` baseline comparison.
- Let GitHub Actions run the PR-scoped performance workflow before merge.
