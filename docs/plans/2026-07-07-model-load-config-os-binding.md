# Model Load Config OS Binding Performance Slice

## Scope

This Python-only performance slice is limited to `services/mlx-worker-python/worker/model_load_trust.py` and the repeated model-load trust policy path that probes `config.json` for custom loader metadata.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for `model_load_trust.py`, `test_model_load_trust.py`, `test_pr_scoped_performance.py`, and `scripts/model_load_config_json_bytes_probe.py`.

## Optimization

Bind the hot OS and stat helpers used by the repeated config probe path at module import time:

- `os.stat` -> `_OS_STAT`
- `os.scandir` -> `_OS_SCANDIR`
- `stat.S_ISREG` -> `_STAT_ISREG`

This keeps trust-policy semantics unchanged while avoiding repeated global attribute resolution in the hot config stat and executable-file fallback paths.

## 2026-07-08 Open Binding Follow-up Slice

This follow-up Python-only slice is still limited to `services/mlx-worker-python/worker/model_load_trust.py` and the registered `model-load-config-json-bytes` probe. The config JSON read path now also binds `builtins.open` as `_OPEN` and uses that module-local binding for the direct binary read in `_read_model_config_for_stat(...)`. The behavior remains identical: config files are opened directly in binary mode, parsed from bytes through `_JSON_LOADS`, and cached by `(path, mtime_ns, size)`.

## 2026-07-09 Trust Constant Binding Follow-up Slice

This follow-up Python-only slice keeps the same `services/mlx-worker-python/worker/model_load_trust.py` boundary and the registered `model-load-config-json-bytes` probe. The repeated trust-policy resolution path now binds the hot protobuf enum constants and the `ModelLoadTrustPolicy` constructor at module import time and uses those local aliases in `_requested_mode(...)`, `_route_class(...)`, hot policy construction, and the trust-mode branch checks. Behavior remains identical; the slice only avoids repeated protobuf module attribute lookups in the config JSON trust-policy hot path.

## 2026-07-19 Runtime Name Direct Attribute Follow-up Slice

This follow-up Python-only slice keeps the same `services/mlx-worker-python/worker/model_load_trust.py` boundary and the registered `model-load-config-json-bytes` probe. The repeated trust-policy resolution path now reads `runtime.runtime_name` through direct attribute access and falls back to `""` only on `AttributeError`, preserving `None`, missing-runtime, string, falsey, and non-string coercion behavior while avoiding the default-argument `getattr(...)` helper call for runtimes that expose the hot `runtime_name` attribute.

Expected metrics are lower `elapsed_ms_mean` and `executable_elapsed_ms_mean` in `scripts/model_load_config_json_bytes_probe.py`; config/executable rejection counts must remain unchanged.

## 2026-07-27 Non-Text Runtime Kind Early Return Follow-up Slice

This follow-up Python-only slice keeps the same `services/mlx-worker-python/worker/model_load_trust.py` boundary and the registered `model-load-config-json-bytes` probe. The trust-applicability helper now returns `False` immediately for runtime kinds outside the text/VLM trust-policy surface, avoiding the lower/replace normalization membership fallback that can only affect text and VLM loaders. Behavior remains identical for supported text/VLM runtime kinds and for non-text/VLM runtimes, which continue to resolve to `not_applicable` unless the runtime explicitly exposes `supports_trust_policy`.

Expected metrics are neutral-to-lower `elapsed_ms_mean` in `scripts/model_load_config_json_bytes_probe.py`; rejection counts must remain unchanged.

## Verification Plan

Run locally on Linux before PR:

1. Focused model-load trust tests and PR-scoped performance probe dispatch tests.
2. Changed-scope coverage using the registered coverage command for `model-load-config-json-bytes`.
3. Registered probe locally with `scripts/model_load_config_json_bytes_probe.py`.
4. `git diff --check`.

GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.
