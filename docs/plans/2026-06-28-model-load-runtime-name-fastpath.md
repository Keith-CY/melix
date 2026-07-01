# Model load trust runtime-name string fast path

## Goal

Reduce per-resolution overhead in model-load trust policy checks by avoiding
generic string coercion when a runtime already exposes a plain string
`runtime_name`.

## Slice

- Keep `resolve_model_load_trust_policy` behavior unchanged for missing,
  falsey, non-string, and string runtime names.
- Add a direct `type(value) is str` return path in `_runtime_name` so the common
  Python runtime objects reuse the existing string object.
- Preserve non-string fallback coercion for compatibility with unusual runtime
  adapters.

## Probe coverage

The affected path is covered by the registered PR-scoped probe
`model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`. The probe
has focused `test_command`, `coverage_command`, and `probe_command` entries and
watches `services/mlx-worker-python/worker/model_load_trust.py`.

## Verification

- Focused model-load trust tests, including `_runtime_name` boundary behavior.
- Changed-scope coverage for `model_load_trust.py` and the probe registry tests.
- Local Linux before/after run of `scripts/model_load_config_json_bytes_probe.py`.
