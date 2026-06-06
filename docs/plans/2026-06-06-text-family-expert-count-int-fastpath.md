# Text Family Expert Count Int Fast Path

## Scope

This Python-only performance slice is limited to `text_family_adapters._expert_count_from_config()` during repeated text-family config resolution.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `text-family-config-copy-elision` in `infra/perf/pr_scoped_probes.json`. The registered entry includes focused `test_command`, `coverage_command`, and `probe_command` values for:

- `services/mlx-worker-python/worker/runtime/text_family_adapters.py`
- `services/mlx-worker-python/tests/test_text_family_adapters.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/text_family_config_probe.py`

## Change

Check the common exact-`int` `num_local_experts` value before the generic `isinstance(..., bool)` / `isinstance(..., int)` chain. Python `bool` remains excluded because the fast path uses `type(value) is int`; existing fallback behavior for bool, float, string, and secondary expert-count keys is preserved.

## Verification plan

1. Run the registered focused pytest command for `text-family-config-copy-elision` locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run `scripts/text_family_config_probe.py` against the `origin/main` baseline and this branch and compare `elapsed_ms_mean`, `peak_bytes_mean`, and `config_copy_calls_mean`.
4. Use the PR-scoped performance workflow as the final CI merge gate before squash merging.

## Metrics

Success is measured by a lower or non-regressing `elapsed_ms_mean` in `scripts/text_family_config_probe.py` with unchanged `peak_bytes_mean` and `config_copy_calls_mean == 0`. This slice has no Swift runtime effect.
