# Model load auto_map leading-character fast path

## Scope

This slice keeps the existing model-load trust policy behavior and optimizes only the hot-path scan used by `_auto_map_has_custom_loader()` for `config.json` `auto_map` entries.

The registered PR-scoped probe `model-load-config-json-bytes` covers `services/mlx-worker-python/worker/model_load_trust.py` and already provides focused `test_command`, `coverage_command`, and `probe_command` entries in `infra/perf/pr_scoped_probes.json`.

## Plan

1. Add a regression guard proving non-empty `auto_map` string values can be accepted from their leading character without calling `str.isspace()` on the common non-blank path.
2. Preserve blank-string and non-string fallback behavior.
3. Re-run the focused registered tests, changed-scope coverage, and `scripts/model_load_config_json_bytes_probe.py` locally on Linux.

## Metrics

- Baseline probe before change: `elapsed_ms_mean=5.88383714369099`, `elapsed_ms_min=5.58217300567776`, `peak_bytes_mean=3251.5714285714284`, `rejections_mean=300.0` (`PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/model_load_config_json_bytes_probe.py`).
- Repeated local baseline/new comparison after change, 3 registered-probe runs each:
  - baseline means: `6.154470428425286`, `5.875594855751842`, `5.73887540459899`; mean `5.9229802295920395` ms.
  - candidate means: `5.718689420193966`, `5.709393274238599`, `6.146521141220417`; mean `5.858201278550994` ms.
  - delta: `-0.06477895104104547` ms (`~1.1058%` lower), rejection count unchanged at `300.0`.
- Acceptance target: lower or neutral `elapsed_ms_mean` and unchanged rejection count under the registered probe.
