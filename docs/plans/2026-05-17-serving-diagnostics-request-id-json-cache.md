# Serving Diagnostics Request-ID JSON Cache

## Scope

This Python-only performance slice targets the serving diagnostics debug queue JSONL serialization path in `services/mlx-worker-python/worker/productization/serving_diagnostics.py`.

The slice is limited to repeated request-id string literal encoding inside `_write_jsonl` / `_empty_attribute_event_json_line` for retained debug queue events. It does not change the diagnostics bundle schema, queue capacity semantics, event ordering, dropped-event accounting, or generated artifacts.

## Probe Coverage

The affected path is already covered by the registered PR-scoped performance probe `serving-diagnostics-debug-queue-bounds` in `infra/perf/pr_scoped_probes.json`.

The registered probe provides:

- `test_command` for focused serving diagnostics tests and PR-scoped probe-selection tests.
- `coverage_command` for changed-scope coverage on the production path, tests, registry selection, and probe script.
- `probe_command` via `scripts/serving_diagnostics_queue_probe.py`, measuring queue append and JSONL serialization metrics.

## Implementation Plan

1. Add a focused regression test proving repeated empty-attribute event serialization reuses encoded request-id literals while preserving JSONL payloads.
2. Thread a per-write request-id literal cache through the fast JSONL event serializer.
3. Keep the fallback `to_dict` serialization path unchanged for events with non-empty attributes, non-float durations, non-int indexes, or non-finite durations.
4. Run focused tests, changed-scope coverage, and the registered local probe on Linux before opening the PR.
5. Use the PR-scoped performance GitHub Actions report as the CI merge gate.

## Expected Metrics

Primary metric: lower `serialization_elapsed_ms_mean` for `serving-diagnostics-debug-queue-bounds`.

Secondary constraints: `elapsed_ms_mean`, `dropped_count`, `retained_count`, `serialization_checksum`, and `serialized_bytes` should remain stable except for normal timing noise.
