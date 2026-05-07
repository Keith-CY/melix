# QAT fake-quant source stats lookup-table optimization

## Goal

Reduce redundant per-byte fake-quant math in QAT source artifact statistics while preserving digest, source byte counts, and quantization-error proxy fields exactly.

## Linux-only constraint

This is a Python-only worker slice under `services/mlx-worker-python`, so it can be locally verified on Linux with focused pytest, changed-scope coverage, and an explicit synthetic performance probe.

## Touched files

- `services/mlx-worker-python/worker/model_ops/quantization_pipeline.py`
- `services/mlx-worker-python/tests/test_quantization_pipeline.py`
- `scripts/qat_fake_quant_source_stats_probe.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Performance probe

Register `qat-fake-quant-source-stats-table-cache` in the PR-scoped performance registry. The probe creates deterministic synthetic source bytes, calls `_qat_fake_quant_source_stats(...)` repeatedly, and reports:

- `elapsed_ms_mean` — lower is better
- `peak_bytes_mean` — informational
- `error_table_builds` — lower is better; expected to be `1.0` across repeated samples
- `source_byte_count` and quant-error fields as structural correctness metrics

## Success metrics

- Focused pytest passes for the QAT stats regression and probe registry tests.
- Changed executable line coverage is at least 95%.
- Local probe shows concrete elapsed/peak metrics and one cached table build across repeated samples.
- `git diff --check` passes.
