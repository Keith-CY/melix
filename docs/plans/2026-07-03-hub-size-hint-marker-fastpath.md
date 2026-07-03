# Hub Catalog Size Hint Marker Fast Path

## Scope

This Python-only performance slice is limited to Hub catalog size-hint parsing in
`services/mlx-worker-python/worker/model_ops/hub_catalog.py`. The behavior stays
unchanged for supported `MODEL SIZE | ...`, `Model size: ...`, and generic
`model size` metadata lines.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`.
The registry entry already defines focused `test_command`, `coverage_command`,
and `probe_command` values and watches:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_size_hint_probe.py`

## Implementation plan

1. Add a tiny direct line parser helper so common exact Hub readme/card marker
   forms can jump directly to value parsing without replaying the generic marker
   whitespace/separator scan.
2. Keep the generic marker path as the fallback for uncommon but currently
   supported forms.
3. Reuse the focused Hub catalog tests, changed-scope coverage command, and the
   registered probe locally on Linux before opening the PR.
4. Use GitHub Actions PR-scoped performance as the final registered-probe merge
   gate.

## Metrics target

Primary metric: `elapsed_ms_mean` from `scripts/hub_catalog_size_hint_probe.py`.
Accept only if the local registered probe shows a clear improvement over the
same-worktree `origin/main` baseline without increasing parser fallbacks or
changing checksum/matched-count outputs.
