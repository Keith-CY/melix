# Hub Catalog Cursor Fast Parse Optimization

## Goal

Reduce transient allocation and redundant string splitting while parsing Hugging Face `Link` headers for the `rel="next"` cursor in `worker/model_ops/hub_catalog.py`.

## Scope

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`

## Linux-only constraint

This is a Python worker slice and can be verified locally on Linux with focused pytest, changed-scope coverage, and the existing PR-scoped performance probe.

## Performance probe

Registered probe: `hub-catalog-next-cursor-fast-parse`

Probe command:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/hub_catalog_next_cursor_probe.py
```

Success metric: lower `elapsed_ms_mean` for repeated cursor parsing while preserving `cursor_parse_calls_mean`, checksum, and decoded cursor values. Peak traced bytes should not materially regress.

## Implementation plan

1. Replace `link_header.split(",")` with a single forward scan over `<...>` link segments so URLs containing commas do not force full header list materialization.
2. Replace query `split("&")` with bounded index scanning for `cursor=` between `?`, `&`, and `#` delimiters.
3. Add focused regression coverage for comma-containing next URLs and cursor parameters without values.
4. Verify with focused tests, changed-scope coverage, local probe, and `git diff --check`.
