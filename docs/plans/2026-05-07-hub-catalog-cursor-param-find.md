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

`_cursor_query_value(...)` currently advances parameter by parameter and checks every parameter start with `startswith("cursor=")`. The cursor parser can instead use a bounded `str.find("cursor=", ..., query_end)` loop and validate the match is at the query start or immediately after `&`. For typical Hub pagination links where `cursor` appears after a few known parameters, this avoids repeated delimiter searches and prefix checks on non-cursor parameters.

## Success metrics

- Focused Hub catalog tests pass, including a boundary regression for `notcursor`/`mycursor` parameters.
- Changed-scope coverage for touched executable Python lines is at least 95%.
- Local base-vs-head probe reports lower `elapsed_ms_mean` without checksum drift.
- The PR-scoped performance workflow runs the registered probe successfully before merge.
