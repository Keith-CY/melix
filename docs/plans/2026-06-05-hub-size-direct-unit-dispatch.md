# Hub catalog direct size-hint unit dispatch

## Scope

Optimize one Python hot path in Hub catalog size-hint parsing:
`worker.model_ops.hub_catalog._direct_size_hint_from_text(...)`.

The direct parser runs for common `cardData.model_size` values before the
generic regular-expression fallback. The current implementation checks each
uppercase and lowercase unit suffix separately before falling back to
`split(maxsplit=2)`. This slice replaces those repeated suffix checks with one
tail-unit dispatch while preserving the whitespace-separated value/unit
contract and the split fallback for unusual unit casing.

## Registered Probe

The affected path is covered by the existing registered PR-scoped probe
`hub-catalog-size-hint-regex-precompile` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_size_hint_probe.py`

## Plan

1. Preserve direct parser behavior for uppercase/lowercase KB, MB, GB,
   fractional values, tab/newline-separated value/unit pairs, invalid units,
   and extra trailing tokens.
2. Dispatch the common tail unit once instead of running six separate
   `endswith(...)` checks.
3. Run the registered focused test command, changed-scope coverage command, and
   local registered probe on Linux.
4. Use GitHub Actions PR-scoped performance output as the merge gate.

## Verification Notes

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
effect is claimed.