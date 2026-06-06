# Text Family Rope Hint Direct Lookup Fast Path

## Scope

This Python-only performance slice is limited to `text_family_adapters._inferred_rope_profile()` during repeated text-family config resolution.

## Probe Coverage

The affected path is already covered by the registered PR-scoped probe `text-family-config-copy-elision` in `infra/perf/pr_scoped_probes.json`. The probe provides focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/text_family_adapters.py`
- `services/mlx-worker-python/tests/test_text_family_adapters.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/text_family_config_probe.py`

## Change

Keep the existing rope-scaling semantics but avoid the generic `_string(...)` helper dispatch on the hot path by checking the resolved `rope_type`/`type` payload directly. The slice also binds `_bool_from_any` locally inside the Yarn branch before checking interleaving flags.

This preserves exact behavior for empty `rope_type` fallbacks, non-string rope hints, `type: yarn`, `interleaved`, and `rope_interleaved` defaults.

## Verification Plan

1. Run the registered focused pytest command for `text-family-config-copy-elision`.
2. Run the registered changed-scope coverage command.
3. Run the registered local probe on Linux at least three times before and after the change and compare `elapsed_ms_mean`, `peak_bytes_mean`, and `config_copy_calls_mean`.
4. Use GitHub Actions PR-scoped performance output as the final merge gate.

## Metrics

Success is measured by non-regressing `elapsed_ms_mean` in `text-family-config-copy-elision`, with unchanged `config_copy_calls_mean` and focused behavior coverage for the rope hint fallback cases.
