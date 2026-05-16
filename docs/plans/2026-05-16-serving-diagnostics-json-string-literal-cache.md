# Serving diagnostics JSON string literal cache

## Scope

Optimize the Python serving diagnostics debug-event JSONL fast path in
`services/mlx-worker-python/worker/productization/serving_diagnostics.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`serving-diagnostics-debug-queue-bounds` in
`infra/perf/pr_scoped_probes.json`. The probe defines focused
`test_command`, `coverage_command`, and `probe_command` entries and reports
queue elapsed time, serialization elapsed time, retained/dropped counts, a
serialization checksum, and serialized byte count.

## Change

The debug queue probe writes thousands of events that commonly reuse the same
`request_id`, `phase`, and `status` strings. The existing empty-attribute JSONL
fast path already builds the row directly, but it still escaped those repeated
string values for every event row. This slice adds a bounded cache around
`json.encoder.encode_basestring_ascii` and uses it only in the direct JSONL event
line path.

Behavior remains unchanged because the cached value is exactly the same escaped
JSON string literal produced by the previous encoder call. The cache is bounded
to avoid unbounded growth if a workload emits high-cardinality identifiers.

## Validation plan

1. Run the focused serving diagnostics tests plus the PR-scoped probe registry
   tests for this probe.
2. Run changed-scope coverage for the changed source path and probe/test files.
3. Run the registered probe locally on Linux against `origin/main` and this
   branch before pushing.
4. Use PR-scoped performance CI as the final registered probe gate before merge.

## Local result

Local Linux probe, `MELIX_SERVING_DIAGNOSTICS_QUEUE_SAMPLES=30`:

- base (`origin/main`): `serialization_elapsed_ms_mean=0.959244`,
  `elapsed_ms_mean=5.504467`
- head: `serialization_elapsed_ms_mean=0.917456`, `elapsed_ms_mean=5.482098`
- serialization delta: `-0.041788 ms` (`-4.36%`)
- checksum and serialized byte count unchanged:
  `serialization_checksum=260064`, `serialized_bytes=10944`
