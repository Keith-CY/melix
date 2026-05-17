# Serving diagnostics JSONL bytearray assembly

## Scope

This Python-only performance slice targets the serving diagnostics event JSONL
writer in `services/mlx-worker-python/worker/productization/serving_diagnostics.py`.
The current path accumulates one Python `str` per event row, joins the list, and
then encodes the entire joined string before writing `events.jsonl`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`serving-diagnostics-debug-queue-bounds` in `infra/perf/pr_scoped_probes.json`.
The registered probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries for the serving diagnostics module, tests, and
`scripts/serving_diagnostics_queue_probe.py`.

## Optimization plan

- Preserve compact JSONL byte layout, key order, ASCII escaping, and fallback
  behavior for non-fast-path events.
- Replace the intermediate list-of-strings plus final `join().encode()` with a
  single `bytearray` buffer that appends encoded rows and newline bytes as rows
  are produced.
- Keep the existing direct event fast path and request-id string literal cache
  unchanged.

## Validation plan

1. Run the focused serving diagnostics tests and PR-scoped performance registry
   tests for this probe.
2. Run changed-scope coverage for the changed source path, focused tests, and
   registered probe script.
3. Run the registered probe locally on Linux against `origin/main` and this
   branch before pushing.
4. Use PR-scoped performance CI as the final registered probe gate before merge.

## Local result

Local Linux registered probe (`serving-diagnostics-debug-queue-bounds`, registry
sample count 20):

- base (`origin/main`): `serialization_elapsed_ms_mean=0.989865`,
  `elapsed_ms_mean=5.498727`
- head: `serialization_elapsed_ms_mean=0.963142`, `elapsed_ms_mean=5.494370`
- serialization delta: `-0.026723 ms` (`-2.70%`)
- checksum and serialized byte count unchanged:
  `serialization_checksum=260064`, `serialized_bytes=10944`
- focused tests and changed-scope coverage passed with 100% changed-line coverage.
