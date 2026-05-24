# Hub catalog next cursor fast parse optimization

## Goal

Reduce per-page overhead in Hugging Face Hub pagination by avoiding full URL and query parsing when Melix only needs the `cursor` value from the RFC 5988 `Link` header's `rel="next"` entry.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python` and is locally verifiable on Linux with focused pytest, changed-scope coverage, and a command-json PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_next_cursor_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Performance probe

Registered probe: `hub-catalog-next-cursor-fast-parse`

The probe parses synthetic Hub `Link` headers repeatedly and emits:

- `elapsed_ms_mean` — lower is better
- `cursor_parse_calls_mean` — structural call-count metric
- `peak_bytes_mean` — lower is better / memory-pressure signal

## Success metrics

- Focused tests pass.
- Changed-scope coverage is at least 95% for touched executable Python scope.
- Local base-vs-head probe preserves cursor parsing correctness and improves elapsed time and/or peak allocation.
- `git diff --check` passes.

## 2026-05-23 slice: direct `rel="next"` marker lookup

This follow-up keeps the same registered probe (`hub-catalog-next-cursor-fast-parse`) and narrows `_next_cursor_from_link()` to search for the `rel="next"` marker first, then locate the immediately preceding bracketed URL with reverse searches. The cursor query parser remains unchanged, preserving boundary handling for `cursor` versus `notcursor`/`mycursor` parameters.

Behavior guard:

- Add a regression case where an encoded `rel="next"` marker appears inside the previous URL; the parser must skip it and use the actual next segment.

Validation remains Linux-local for Python tests, changed-scope coverage, and the registered command-json probe; CI must rerun the registered probe before merge.
