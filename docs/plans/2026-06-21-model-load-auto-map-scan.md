# Model load auto-map detection performance slice

## Scope

This Python-only performance slice is limited to custom-loader `auto_map`
detection in `worker.model_load_trust._detect_custom_loader_requirement()`.

## Change

`resolve_model_load_trust_policy(...)` reads `config.json` for applicable
text/VLM model loads and checks `auto_map` values to decide whether a custom
loader requires `trust_remote_code`. The previous scan used a generator with
`str(value or "").strip()` for every value, which coerced ordinary non-empty
string values and allocated a stripped copy even for the common custom-loader
case.

This slice replaces that generator with `_auto_map_has_custom_loader(...)`, a
single explicit loop that:

- returns immediately for the first non-empty loader value;
- avoids `str(...)` coercion for existing string values;
- uses `str.isspace()` for blank-string preservation without allocating a
  stripped copy;
- keeps the previous fallback behavior for non-string values.

## Probe coverage

The affected path is covered by the registered PR-scoped probe
`model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/model_load_trust.py`
- `services/mlx-worker-python/tests/test_model_load_trust.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/model_load_config_json_bytes_probe.py`

## Local validation plan

Run on Linux:

1. The registered focused test command for `model-load-config-json-bytes`.
2. The registered changed-scope coverage command for the same probe.
3. The registered probe command before and after implementation, using repeated
   samples and the default probe workload.

## Expected effect

Accept only if behavior tests and changed-scope coverage pass and the registered
probe shows directionally lower elapsed time without introducing a regression in
rejection counts or config parsing behavior.
