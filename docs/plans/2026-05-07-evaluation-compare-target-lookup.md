# Evaluation Compare Target Lookup Early Stop

## Goal

Reduce redundant loaded-model lookups in `resolve_compare_target_models()` when evaluation compare requests a small set of target model IDs from a registry with many resident models.

## Scope

- `services/mlx-worker-python/worker/productization/evaluation_compare.py`
- `services/mlx-worker-python/tests/test_evaluation_core.py`
- `infra/perf/pr_scoped_probes.json`

## Linux verification path

This is a Python-only optimization and is verifiable on Linux with focused pytest, changed-scope coverage, `git diff --check`, and a registered PR-scoped performance probe.

## Optimization

The current resolver builds a dictionary for every loaded model before checking the requested target IDs. The optimized resolver will:

1. Convert requested target IDs to a set.
2. Store only loaded models whose IDs are requested.
3. Stop scanning once all requested targets have been resolved.
4. Preserve duplicate target ordering and unknown-target errors.

## Probe

Register `evaluation-compare-target-lookup-early-stop` in `infra/perf/pr_scoped_probes.json` with a synthetic registry containing many loaded handles and a small requested target set near the front of the scan. The probe reports elapsed time and `get_loaded_model` calls; lower is better for both.

## Success metrics

- Focused tests pass.
- Changed executable line coverage is at least 95%.
- Local probe shows fewer registry lookups and lower elapsed time versus `origin/main`.
- The registered PR-scoped performance CI probe completes successfully before merge.
