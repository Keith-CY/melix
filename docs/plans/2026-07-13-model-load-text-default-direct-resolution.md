# Model load text default direct resolution fast path

## Scope

This Python-only performance slice is limited to `services/mlx-worker-python/worker/model_load_trust.py` and the common text-runtime policy path where the request has no explicit load-trust policy, the model spec has no explicit settings, and the route class is unspecified.

## Probe Coverage

The affected path is covered by the registered PR-scoped performance probe `model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_load_trust.py`
- `services/mlx-worker-python/tests/test_model_load_trust.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/model_load_config_json_bytes_probe.py`

## Plan

1. Add a focused regression test proving the common text/default policy path bypasses the generic requested-mode and loader-family helpers while preserving the emitted policy fields.
2. Keep the generic policy flow unchanged, but add a direct common-path branch that preserves the same rejection/policy field semantics without calling the generic requested-mode and loader-family helpers.
3. Keep all explicit request-policy, model-settings, VLM, and non-applicable paths on the existing generic resolution flow.
4. Run the registered focused tests, changed-scope coverage, and registered local probe on Linux before opening the PR.
5. Use GitHub Actions PR-scoped performance as the merge gate for the registered probe report.

## Validation Notes

Local Linux validation covers the Python implementation and registered Python probe. No Swift runtime effect is claimed for this slice.
