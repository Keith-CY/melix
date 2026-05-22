# Code Eval Payload Monotonic Fast Path Slice

## Scope

Optimize the Python code-evaluation payload JSON fast path in
`services/mlx-worker-python/worker/engine/code_eval_runner.py`.

## Probe Coverage

The affected path is already covered by the registered PR-scoped probe
`code-eval-payload-json-bytes` in `infra/perf/pr_scoped_probes.json`.
The probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries and watches:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_payload_json_probe.py`

## Change

The fast-path field extractor now treats the recognized payload layouts as
monotonic key-order layouts. It no longer performs per-field whole-payload
fallback searches after the scan cursor has advanced. Unexpected key order still
falls back to the full JSON loader, preserving correctness for non-standard
payloads.

For sorted payloads without `compile_status`, the fast path skips the optional
`compile_status` token lookup. Runner payloads that start with `compile_status`
still extract that field, including when object-leading whitespace is present.

## Local Evidence

Baseline local Linux probe before the change:

- `elapsed_ms_mean`: 123.218, 118.213, 125.161 ms
- `peak_bytes_mean`: 60425 bytes

Post-change local Linux probe:

- `elapsed_ms_mean`: 99.466, 94.525, 93.470 ms
- `peak_bytes_mean`: 60425 bytes

This slice reduces local probe elapsed mean from about 122.2 ms to about
95.8 ms across three runs, a roughly 21.6% improvement, with unchanged peak
allocation metric.

## Verification Boundary

This is a Python slice and is locally verified on Linux. The registered
PR-scoped performance workflow remains the authoritative CI validation before
merge.
