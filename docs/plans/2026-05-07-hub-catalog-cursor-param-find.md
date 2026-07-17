# Hub Catalog Cursor Parameter Bounded Find

## Goal

Reduce repeated query-parameter boundary scanning in the Hub catalog `Link` header cursor parser while preserving the exact `cursor` parameter semantics.

## Scope

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `docs/plans/2026-05-07-hub-catalog-cursor-param-find.md`

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python` and is verified locally on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped performance probe.

## Registered performance probe

Use the existing registered probe `hub-catalog-next-cursor-fast-parse` in `infra/perf/pr_scoped_probes.json`. The probe covers `services/mlx-worker-python/worker/model_ops/hub_catalog.py`, focused Hub catalog tests, changed-scope coverage, and `scripts/hub_catalog_next_cursor_probe.py`.

## Optimization hypothesis

`_next_cursor_from_link(...)` can avoid allocating a sliced URL string for the `rel="next"` segment by passing the segment bounds into `_cursor_query_value(...)`. The cursor helper keeps the same exact-parameter semantics but searches only within the bounded URL range and looks for the two legal cursor parameter prefixes: `cursor=` at the beginning of the query string or `&cursor=` later in the query. This preserves boundary behavior for parameters such as `notcursor` and `mycursor` while reducing transient cursor-parse work.

## Success metrics

- Focused Hub catalog tests pass, including a boundary regression for `notcursor`/`mycursor` parameters.
- Changed-scope coverage for touched executable Python lines is at least 95%.
- Local base-vs-head probe reports lower `elapsed_ms_mean` without checksum drift.
- The PR-scoped performance workflow runs the registered probe successfully before merge.

## 2026-07-17 ampersand cursor fast path

This follow-up Python-only slice keeps the same registered `hub-catalog-next-cursor-fast-parse` probe and narrows to `_next_cursor_from_link(...)`. The common Hugging Face next-link URL places `cursor` after earlier query parameters (`...&cursor=...`), so the parser now checks the query-start `cursor=` case once and otherwise searches directly for the bounded `&cursor=` parameter. This removes the repeated generic `cursor=` substring scan and previous-character boundary check in the common path while preserving exact query-parameter behavior for `cursor` at query start, `notcursor`/`mycursor`, fragment boundaries, and encoded cursor decoding.
