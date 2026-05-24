# LoRA auxiliary module scan with scandir

## Scope

This Python-only performance slice is limited to `worker.model_ops.lora_runtime_metadata._aux_modules_restored()`, which feeds LoRA canary receipt fields for checkpoint resume assets.

## Registered probe

This slice adds the registered PR-scoped probe `lora-aux-module-scan-scandir` in `infra/perf/pr_scoped_probes.json`. The probe covers:

- `services/mlx-worker-python/worker/model_ops/lora_runtime_metadata.py`
- `services/mlx-worker-python/tests/test_lora_training_receipts.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/lora_aux_module_scan_probe.py`

The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries. Local Linux can validate the Python behavior and probe metrics; GitHub Actions remains the merge gate for the registered PR-scoped performance report.

## Change

Replace four `Path.glob()` scans for auxiliary module patterns (`modeling_*.py`, `configuration_*.py`, `tokenization_*.py`, `processing_*.py`) with one `os.scandir()` pass over the base model directory and precomputed prefix/suffix matchers.

## Verification plan

1. Run focused LoRA canary receipt and PR-scoped probe selection tests.
2. Run changed-scope coverage through the registered coverage command.
3. Run the registered probe locally on Linux.
4. Push the PR and require the PR-scoped performance CI probe to complete successfully before merge.

## Metrics

Primary metric: `elapsed_ms_mean` from `scripts/lora_aux_module_scan_probe.py`.

Secondary metrics: `hit_count_mean`, `filler_file_count`, `iterations`, and `sample_count`.
