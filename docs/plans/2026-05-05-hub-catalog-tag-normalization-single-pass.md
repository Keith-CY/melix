# Hub Catalog Tag Normalization Single Pass

## Goal

Reduce repeated tag normalization while building Hugging Face Hub catalog summary records.

## Scope

Touched files:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `scripts/hub_catalog_tag_normalization_probe.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Linux-only Constraint

This is a Python-only worker metadata path and can be verified on Linux with focused pytest, changed-scope coverage, and a local synthetic performance probe.

## Probe

Registered PR-scoped performance probe:

- `hub-catalog-tag-normalization-single-pass`

The probe builds synthetic Hub model payloads and compares base vs head for:

- `tag_normalization_calls_mean` (lower is better, structural metric)
- `elapsed_ms_mean` (lower is better)

The probe also emits `peak_bytes_mean` as observational context, but the CI gate uses the structural call-count and elapsed-time signals because the head-side helper instrumentation intentionally counts calls through a monkeypatched wrapper.

## Success Metrics

- Preserve Hub catalog output semantics for MLX compatibility, quantization summary, and resident-byte estimates.
- Avoid card-data tag normalization when an earlier MLX compatibility signal already proves the record is compatible.
- Keep changed-scope automated coverage at or above 95%.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_tag_normalization_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_tag_normalization_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/hub_catalog.py services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/hub_catalog_tag_normalization_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/hub_catalog_tag_normalization_probe.py
```
