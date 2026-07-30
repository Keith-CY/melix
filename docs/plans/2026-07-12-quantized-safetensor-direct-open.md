# Quantized safetensors header direct-open slice

This Python-only performance slice is limited to `worker.runtime.quantized_tensor_metadata.quantized_tensor_metadata_from_safetensor_headers()` and its private safetensors header reader.

## Scope

The registered quantized metadata prepass probe exercises safetensors header discovery for native multimodal tensor metadata. The hot path receives shard paths from `os.scandir()` as strings when the model directory has no index payload. Before this slice, each shard path was wrapped in `Path` only so `_safetensors_header_tensor_names()` could call `Path.open()`.

This slice keeps behavior unchanged while passing the normalized filesystem string directly into the header reader and using direct `open(path, "rb")`. It avoids one `Path` object allocation per safetensors shard during header prepass.

## Probe coverage

The affected path is covered by the registered PR-scoped probe `quantized-tensor-metadata-prepass` in `infra/perf/pr_scoped_probes.json`. The registry entry already includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches:

- `services/mlx-worker-python/worker/runtime/quantized_tensor_metadata.py`
- `services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/quantized_tensor_metadata_prepass_probe.py`

## Verification plan

1. Add a regression test proving string shard paths do not rely on `Path.open()` for safetensors header reads.
2. Run the registered focused tests for `quantized-tensor-metadata-prepass` locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux and require at least 95% for touched scope.
4. Run the registered probe command locally on Linux and compare base-vs-head metrics.
5. Use GitHub Actions PR-scoped performance as the final registered probe merge gate.

## Expected metrics

Primary metric: lower `elapsed_ms_mean` / `elapsed_ms_min` / `elapsed_ms_p95` for safetensors header metadata prepass with unchanged tensor counts and fixup counts.

## Boundaries

This slice does not change quantization policy, tensor-name normalization, index-payload handling, generated protobuf artifacts, or Swift/runtime behavior.
