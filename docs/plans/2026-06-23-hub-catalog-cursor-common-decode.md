# Hub catalog cursor common decode slice

## Scope

This Python-only performance slice is limited to the Hub catalog `Link` header
cursor decoder in `services/mlx-worker-python/worker/model_ops/hub_catalog.py`.
It preserves existing query-boundary scanning behavior and narrows only the
common Hugging Face cursor decode path.

## Probe coverage

The affected path is already covered by the registered PR-scoped performance
probe `hub-catalog-next-cursor-fast-parse` in
`infra/perf/pr_scoped_probes.json`. The registration includes focused
`test_command`, `coverage_command`, and `probe_command` entries covering:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_next_cursor_probe.py`

## Implementation plan

1. Add a fast decode branch for cursor values containing only the common
   `%2F` / `%2B` escapes plus `+` spaces.
2. Keep the existing manual percent decoder and `urllib.parse.unquote_plus`
   fallback for uncommon percent escapes, UTF-8, and malformed values.
3. Add a focused regression test for lowercase common cursor escapes.
4. Run focused tests, changed-scope coverage, and the registered probe locally
   on Linux, then use GitHub Actions PR-scoped performance as the merge gate.

## Expected signal

The registered probe repeatedly parses Hugging Face-style next-cursor Link
headers whose cursor value contains `%2F`, `%2B`, and `+`. The expected signal is
lower `elapsed_ms_mean` by using CPython string replace operations for the common
ASCII cursor escape set while preserving fallback behavior for other encodings.