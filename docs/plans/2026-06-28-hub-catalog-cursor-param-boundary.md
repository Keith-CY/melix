# Hub catalog cursor parameter boundary scan

## Scope

This Python-only performance slice is limited to `worker.model_ops.hub_catalog._next_cursor_from_link(...)` and its focused regression coverage. It does not change Hub request construction, summary/card model semantics, generated protocol artifacts, or Swift runtime behavior.

## Registered probe

The affected path is already covered by the registered PR-scoped performance probe `hub-catalog-next-cursor-fast-parse` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_next_cursor_probe.py`

## Slice plan

1. Keep the existing direct Link-header scanner and avoid reintroducing `urlparse` or `parse_qs` allocations.
2. Replace the two-stage `?` / `&cursor=` lookup with a bounded `cursor=` scan that accepts only query-parameter boundaries (`?cursor=` or `&cursor=`) before the URL fragment.
3. Add regression coverage showing cursor-like substrings in the path, other parameter names, and fragment are ignored.
4. Verify with the registered focused tests, changed-scope coverage, and local registered probe on Linux, then use PR-scoped performance CI as the merge gate.

## Metrics

The success metric is the registered probe's `elapsed_ms_mean` for repeated `_next_cursor_from_link(...)` calls. `peak_bytes_mean` remains monitored. This is a Python-only slice and is locally verifiable on Linux; no Swift runtime effect is claimed.
