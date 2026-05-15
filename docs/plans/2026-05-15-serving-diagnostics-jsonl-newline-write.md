# Serving diagnostics JSONL newline write slice

## Goal

Reduce debug serving diagnostics JSONL serialization overhead for bounded event
queue captures without changing the JSONL payload or diagnostics bundle layout.

## Probe coverage

The affected path is covered by the registered PR-scoped probe
`serving-diagnostics-debug-queue-bounds` in `infra/perf/pr_scoped_probes.json`.
That probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/productization/serving_diagnostics.py`
- `services/mlx-worker-python/tests/test_serving_diagnostics.py`
- `scripts/serving_diagnostics_queue_probe.py`

## Slice

`_write_jsonl` now writes the encoded JSON payload and newline separately. This
avoids allocating a fresh concatenated string for every diagnostics event row
while preserving the exact byte output.

## Local evidence

Linux local probe with `MELIX_SERVING_DIAGNOSTICS_QUEUE_SAMPLES=9`:

- base `serialization_elapsed_ms_mean=1.382938`, `elapsed_ms_mean=5.729605`
- head `serialization_elapsed_ms_mean=1.215733`, `elapsed_ms_mean=5.759658`
- serialization delta `-0.167205 ms` (`-12.09%`)
- `serialized_bytes=10880` and `serialization_checksum=260064` on both base and head

Focused tests and changed-scope coverage passed locally with 100% changed-line
coverage for the modified lines.
