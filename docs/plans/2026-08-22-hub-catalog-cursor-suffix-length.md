# Hub catalog cursor suffix length binding

## Slice

This Python-only performance slice is limited to the Hub catalog pagination cursor parser in `services/mlx-worker-python/worker/model_ops/hub_catalog.py`.

The common Hugging Face `Link` header shape ends with the `>; rel="next"` suffix. `_next_cursor_from_link(...)` already has a suffix fast path; this slice precomputes the suffix length beside the suffix constant so the repeated parser loop does not call `len(...)` for the invariant marker on every cursor parse.

## Registered performance probe

The affected path is covered by the registered PR-scoped probe `hub-catalog-next-cursor-fast-parse` in `infra/perf/pr_scoped_probes.json`. The registry entry has focused `test_command`, `coverage_command`, and `probe_command` entries and watches the Hub catalog parser, focused tests, and probe script.

The primary metric is `elapsed_ms_mean` from `scripts/hub_catalog_next_cursor_probe.py`; `peak_bytes_mean` and `cursor_parse_calls_mean` are regression guards.

## Verification plan

1. Keep behavior unchanged and rely on the existing Hub catalog cursor parser tests for suffix, middle-link, missing-cursor, fragment, first-parameter, plus-space, percent-decoding, and fallback cases.
2. Apply only the suffix-length binding in `_next_cursor_from_link(...)`.
3. Run the registered focused pytest command locally on Linux.
4. Run changed-scope coverage for the registered probe locally on Linux.
5. Run the registered `hub-catalog-next-cursor-fast-parse` probe locally against `origin/main` and this branch.
6. Use GitHub Actions PR-scoped performance as the final registered probe validation and merge gate.
