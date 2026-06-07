# QAT fake-quant source stats read binding slice

## Scope

This Python-only performance slice is limited to `_qat_fake_quant_source_stats` in `services/mlx-worker-python/worker/model_ops/quantization_pipeline.py`.

The source-stats hot path streams source artifact bytes, updates a SHA-256 digest, translates bytes through the cached fake-quant error table, and aggregates the error sum/max. This slice keeps the existing digest, byte-count, mean, and max semantics while reducing repeated loop overhead with local method bindings and avoiding redundant translated-error max scans after the theoretical maximum error unit has already been observed.

## Registered Probe

Registered PR-scoped probe: `quantization-qat-source-scan-scandir` in `infra/perf/pr_scoped_probes.json`.

The registry entry covers the affected quantization pipeline, focused quantization tests, PR-scoped performance tests, and `scripts/quantization_qat_source_scan_probe.py`. It already provides focused `test_command`, `coverage_command`, and `probe_command` entries. The local Linux probe reports both source artifact scanning metrics and `source_stats_elapsed_ms_mean` for this slice.

## Verification Plan

- Add/keep focused regression coverage for QAT source stats digest/count/mean/max behavior, including payloads that do not contain the global table maximum.
- Run the registered focused `test_command` locally on Linux.
- Run the registered changed-scope `coverage_command` locally on Linux.
- Run the registered `probe_command` locally on Linux before and after implementation and compare `source_stats_elapsed_ms_mean`.
- Use GitHub Actions PR-scoped performance as the merge gate.

## Expected Metrics

The probe should preserve behavior and reduce `source_stats_elapsed_ms_mean` by lowering Python-level work inside the byte-streaming loop. Directory scan metrics are expected to remain unchanged because this slice does not alter `_source_artifact_files_for_qat`.
