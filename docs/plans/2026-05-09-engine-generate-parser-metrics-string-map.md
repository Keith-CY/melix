# Engine Generate Parser Metrics String Map Optimization

## Goal

Avoid building an intermediate parser-metrics dictionary with object values and a second stringifying dictionary when finalizing Python generate requests. The optimized path stringifies existing stream-assembler metrics once, then writes the three engine-owned parser metric keys directly as strings.

## Scope

- `services/mlx-worker-python/worker/engine/engine_core.py`
- `services/mlx-worker-python/tests/test_generate_stream.py`
- `docs/plans/2026-05-09-engine-generate-parser-metrics-string-map.md`

## Linux-only constraint

This slice is Python-only and is locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered command-json PR-scoped performance probe. No Swift/macOS runtime effect is claimed.

## Registered probe

The affected path is covered by the existing registered PR-scoped probe `engine-generate-usage-token-elision` in `infra/perf/pr_scoped_probes.json`. That registry entry already includes focused `test_command`, `coverage_command`, and `probe_command` values for the Python generate no-usage hot path.

## Success metrics

- Focused generate-stream tests pass and prove parser metric values remain string-valued.
- Changed-scope coverage for touched Python executable lines is at least 95%.
- The registered local probe reports a non-regressive or improved `elapsed_ms_mean` for repeated generate requests.
- `git diff --check` passes.
