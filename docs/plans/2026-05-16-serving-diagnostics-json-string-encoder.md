# Serving diagnostics JSON string encoder fast path

## Scope

This Python-only performance slice targets the default-attribute serving
diagnostics event JSONL fast path in
`services/mlx-worker-python/worker/productization/serving_diagnostics.py`.
The previous fast path used a dedicated `JSONEncoder(...).encode` bound method
for each event string field even though only JSON string escaping is needed.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`serving-diagnostics-debug-queue-bounds` in
`infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`,
`coverage_command`, and `probe_command` entries for the serving diagnostics
module, tests, and `scripts/serving_diagnostics_queue_probe.py`.

## Optimization plan

- Preserve the compact JSONL byte layout, sorted key order, and ASCII escaping
  behavior of the default-attribute event fast path.
- Replace the generic JSONEncoder string encode bound method with
  `json.encoder.encode_basestring_ascii`, which directly performs the same
  string escaping used by the default JSON encoder.
- Extend the focused JSONL fast-path regression test to include non-ASCII text
  so the optimized encoder continues to prove ASCII escape parity.

## Local evidence

Linux local probe with `MELIX_SERVING_DIAGNOSTICS_QUEUE_SAMPLES=30`:

- base (`origin/main`): `serialization_elapsed_ms_mean=1.049969`,
  `elapsed_ms_mean=5.881154`
- head: `serialization_elapsed_ms_mean=0.884999`, `elapsed_ms_mean=5.347447`
- serialization delta: `-0.164970 ms` (`-15.71%`)
- `serialization_checksum=260064` and `serialized_bytes=10944` on both base and head

Focused tests, changed-scope coverage, and `ruff check` passed locally on Linux.
CI PR-scoped performance remains the merge gate.
