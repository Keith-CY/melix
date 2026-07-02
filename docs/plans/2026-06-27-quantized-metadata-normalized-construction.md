# Quantized tensor metadata normalized construction slice

This Python performance slice is limited to quantized tensor metadata construction
inside `worker.runtime.quantized_tensor_metadata`. The runtime already normalizes
index/header tensor mappings before wrapping them in `QuantizedTensorMetadata`;
this slice removes the second normalization pass while preserving immutable
`MappingProxyType` exposure.

## Registered probe

The affected path is covered by the existing PR-scoped probe
`quantized-tensor-metadata-prepass` in `infra/perf/pr_scoped_probes.json`. The
probe includes focused `test_command`, `coverage_command`, and `probe_command`
entries for:

- `services/mlx-worker-python/worker/runtime/quantized_tensor_metadata.py`
- `services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/quantized_tensor_metadata_prepass_probe.py`

## Slice

- Add an internal constructor for already-normalized `dict[str, str]` metadata.
- Reuse it from index-payload and safetensors-header construction to avoid
  re-stringifying keys and shard names in `QuantizedTensorMetadata.__post_init__`.
- Iterate `tensor_to_shard` directly in cross-shard fixup counting to avoid an
  extra `frozenset` allocation.
- Preserve the public dataclass constructor behavior for arbitrary external
  mappings and keep returned metadata immutable.

## Local verification

Run the registered focused test command, changed-scope coverage command, and
registered probe locally on Linux before pushing. Compare the registered probe
against `origin/main` and this branch; the accepted signal is lower index/header
construction elapsed time and peak bytes with unchanged tensor counts and
cross-shard counts.
