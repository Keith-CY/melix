# Hub catalog next-link parser local bindings

## Slice

This Python-only performance slice is limited to the Hub catalog pagination cursor parser in `services/mlx-worker-python/worker/model_ops/hub_catalog.py`.

The parser repeatedly scans for invariant marker/query strings while extracting the next cursor. This slice precomputes the fallback `rel="next"` marker length beside the marker constant and binds the query parser's repeated string-search constants through function defaults, preserving parser behavior while reducing per-call global lookups in the repeated parse loop.

## Registered performance probe

The affected path is covered by the registered PR-scoped probe `hub-catalog-next-cursor-fast-parse` in `infra/perf/pr_scoped_probes.json`. The registry entry has focused `test_command`, `coverage_command`, and `probe_command` entries and watches the Hub catalog parser, focused tests, the probe script, and the prior cursor parser plan.

The primary metric is `elapsed_ms_mean` from `scripts/hub_catalog_next_cursor_probe.py`; `peak_bytes_mean` and `cursor_parse_calls_mean` are regression guards. This slice also extends the probe input mix to alternate between the common suffix fast path and a middle-link fallback shape so the registered probe directly measures the marker-length fallback branch touched here.

## Verification plan

1. Keep behavior unchanged and rely on the existing Hub catalog cursor parser tests for suffix, middle-link, missing-cursor, fragment, first-parameter, plus-space, percent-decoding, and fallback cases.
2. Apply only local bindings in the next-cursor parser and query-value helper.
3. Run the registered focused pytest command locally on Linux.
4. Run changed-scope coverage for the registered probe locally on Linux.
5. Run the registered `hub-catalog-next-cursor-fast-parse` probe locally against the pre-change branch state and this branch.
6. Use GitHub Actions PR-scoped performance as the final registered probe validation and merge gate.