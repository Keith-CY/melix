# Model Load Auto-Map Leading ASCII Fast Path

## Scope

This Python-only performance slice is limited to `_auto_map_has_custom_loader(...)` in `services/mlx-worker-python/worker/model_load_trust.py`. It preserves custom-loader detection semantics for empty strings, ASCII whitespace-only strings, Unicode whitespace-only strings, non-string fallback values, and common non-empty `auto_map` strings.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `Model load config JSON bytes` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and selects this probe when `services/mlx-worker-python/worker/model_load_trust.py`, related tests, or `scripts/model_load_config_json_bytes_probe.py` changes.

## Optimization

The hot probe payload uses `auto_map` values like `"custom.Loader"`. Instead of calling `value[0].isspace()` for the common leading printable ASCII case, check `value[0] > " "` first and return immediately. Values whose first character is not printable ASCII still fall through to the existing whitespace-preserving checks, including Unicode whitespace.

## Verification Plan

1. Add focused regression coverage for Unicode whitespace-only `auto_map` strings so the printable-ASCII fast path cannot change blank-string semantics.
2. Run the registered focused test command locally on Linux.
3. Run changed-scope coverage for the registered model-load probe scope and require at least 95% coverage for touched executable scope.
4. Run the registered probe locally on Linux before and after the change and compare repeated `elapsed_ms_mean` samples.
5. Use GitHub Actions PR-scoped performance as the merge gate.

## Baseline

Local Linux baseline on `origin/main`, `scripts/model_load_config_json_bytes_probe.py` repeated three times:

- `elapsed_ms_mean=6.085972717430975`, `peak_bytes_mean=3194.285714285714`, `rejections_mean=300.0`
- `elapsed_ms_mean=5.696465859987906`, `peak_bytes_mean=3194.285714285714`, `rejections_mean=300.0`
- `elapsed_ms_mean=5.9100692867234885`, `peak_bytes_mean=3194.285714285714`, `rejections_mean=300.0`

Mean baseline `elapsed_ms_mean=5.89750262138079` ms.

## Candidate Metrics

Local Linux candidate on this branch, `scripts/model_load_config_json_bytes_probe.py` repeated three times:

- `elapsed_ms_mean=5.782281855187778`, `peak_bytes_mean=3194.285714285714`, `rejections_mean=300.0`
- `elapsed_ms_mean=5.56336300048445`, `peak_bytes_mean=3194.285714285714`, `rejections_mean=300.0`
- `elapsed_ms_mean=5.701765139487439`, `peak_bytes_mean=3194.285714285714`, `rejections_mean=300.0`

Mean candidate `elapsed_ms_mean=5.682469998386556` ms. Delta vs baseline: `-0.21503262299423387` ms (`~3.6462%` lower). `rejections_mean` remained `300.0` and `peak_bytes_mean` remained `3194.285714285714`.

## Linux Validation Boundary

This slice only changes Python worker code and is locally verifiable on Linux. No Swift runtime effect is claimed.
