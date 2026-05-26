# Quantization smoke required-file single directory scan

## Scope

This Python performance slice is limited to `_smoke_required_files_for_backend(...)` in `worker.model_ops.quantization_pipeline`. It does not change quantization conversion, manifest generation, smoke execution, or safetensors index parsing.

## Registered probe

Existing registered PR-scoped probe: `quantization-index-shard-min-single-pass` in `infra/perf/pr_scoped_probes.json`.

The probe covers:

- `services/mlx-worker-python/worker/model_ops/quantization_pipeline.py`
- `services/mlx-worker-python/tests/test_quantization_pipeline.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/quantization_index_shard_probe.py`

The registry defines focused `test_command`, `coverage_command`, and `probe_command` entries for Linux CI, so no probe registry change is needed.

## Optimization

The MLX-LM smoke required-file helper previously probed tokenizer and weight marker files with separate `Path.exists()` calls before reading the safetensors index. This slice replaces those repeated path stats with one `os.scandir()` pass over the bundle directory, preserving the existing priority order: `tokenizer.json` before `tokenizer.model`, and `model.safetensors` before `model.safetensors.index.json`.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux before opening the PR. The PR-scoped performance workflow remains the merge gate for the registered probe result in CI.

## Success criteria

- Focused quantization helper tests pass.
- Changed-scope coverage remains at or above 95% for the touched Python paths.
- The registered probe shows lower `elapsed_ms_mean` on the same synthetic sharded bundle workload.
- `git diff --check` passes.
