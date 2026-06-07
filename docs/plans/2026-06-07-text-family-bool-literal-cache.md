# Text Family Bool Literal Cache

## Scope

This Python-only performance slice is limited to `text_family_adapters._bool_from_any()` during repeated text-family config resolution.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `text-family-config-copy-elision` in `infra/perf/pr_scoped_probes.json`. The registered entry includes focused `test_command`, `coverage_command`, and `probe_command` values for:

- `services/mlx-worker-python/worker/runtime/text_family_adapters.py`
- `services/mlx-worker-python/tests/test_text_family_adapters.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/text_family_config_probe.py`

## Change

Hoist the truthy and falsy string literal sets used by `_bool_from_any()` to module-level frozensets. This preserves the accepted string variants while avoiding per-call set construction on the repeated config-resolution path.

## Verification plan

1. Run the registered focused pytest command for `text-family-config-copy-elision` locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run `scripts/text_family_config_probe.py` against the `origin/main` baseline and this branch and compare `elapsed_ms_mean`, `peak_bytes_mean`, and `config_copy_calls_mean`.
4. Use the PR-scoped performance workflow as the final CI merge gate before squash merging.

## Metrics

Success is measured by a lower or non-regressing `elapsed_ms_mean` in `scripts/text_family_config_probe.py` with unchanged `config_copy_calls_mean == 0`. This slice has no Swift runtime effect.
