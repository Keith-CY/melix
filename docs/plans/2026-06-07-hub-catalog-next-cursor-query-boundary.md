# Hub catalog next-cursor query-boundary slice

This Python-only performance slice is limited to `worker.model_ops.hub_catalog._next_cursor_from_link(...)`.

## Scope

The hub catalog scans Hugging Face `Link` headers to extract the `rel="next"` cursor without importing `urlparse`/`parse_qs`. The current implementation first finds the next-link URL bounds and then calls the generic `_cursor_query_value(...)` helper, which performs a second query-marker scan from the start of that URL.

This slice preserves the existing header parsing behavior while reusing the already-known next-link URL boundary to locate the query marker once and parse the `cursor` value directly inside `_next_cursor_from_link(...)`. It also adds an ASCII percent-decoding fast path for the cursor values emitted by the Hub pagination API while retaining the existing `urllib.parse.unquote_plus(...)` fallback for non-ASCII percent escapes.

## Registered probe

The affected path is covered by the registered PR-scoped probe `hub-catalog-next-cursor-fast-parse` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_next_cursor_probe.py`

The probe reports `elapsed_ms_mean`, `cursor_parse_calls_mean`, and `peak_bytes_mean` for repeated encoded cursor extraction.

## Verification plan

Run the registered focused tests, changed-scope coverage command, and local registered probe on Linux before opening the PR. CI remains the merge gate for the registered PR-scoped performance report.
