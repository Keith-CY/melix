# Hub Catalog Size-Hint Multiplier Constants

## Goal

Avoid repeated power-expression evaluation while parsing Hub catalog model-size hints by reusing module-level byte multiplier constants for KB, MB, and GB units.

## Touched Files

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`

## Linux-Only Constraint

This slice is Python-only and can be verified locally on Linux with focused pytest, changed-scope coverage, and the existing PR-scoped performance probe.

## Performance Probe

Use the existing registered probe:

- `hub-catalog-size-hint-regex-precompile`

The probe builds synthetic Hub catalog size-hint payloads and exercises both direct `cardData.model_size` parsing and labeled text parsing. The registered probe has focused `test_command`, `coverage_command`, and `probe_command` entries in `infra/perf/pr_scoped_probes.json`.

## Success Metrics

- Focused Hub catalog tests pass.
- Changed executable line coverage for touched Python scope is at least 95%.
- The local base-vs-head registered probe reports behavior parity and lower mean elapsed time for the size-hint workload.

## Implementation Plan

1. Add module-level byte multiplier constants and reuse them in `_direct_size_hint_from_text(...)` and `_size_hint_from_text(...)`.
2. Extend the focused size-hint parser test to cover KB, fractional MB, and GB through both direct and regex-backed paths.
3. Run focused pytest, changed-scope coverage, `git diff --check`, and the registered local probe before opening the PR.
