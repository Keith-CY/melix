# Native MTP loader safetensor scandir slice

## Scope

Replace the native-MTP loader's top-level `model*.safetensors` glob with a
single `os.scandir()` pass. This path is exercised only when sidecar MTP shards
are present and the loader falls back to the custom `mlx-lm` model-load path.

## Probe

Registered PR-scoped probe: `native-mtp-loader-safetensor-scandir` in
`infra/perf/pr_scoped_probes.json`.

The probe builds a synthetic model directory containing base model shard files,
MTP sidecar shard files, and distractor entries, then compares:

- old behavior: `glob.glob(str(model_dir / "model*.safetensors"))` plus file filtering
- new behavior: `_model_safetensor_files(model_dir)` backed by `os.scandir()`

Metrics:

- `old_mean_ms`
- `new_mean_ms`
- `delta_ms`
- `speedup`
- `old_peak_bytes_mean`
- `new_peak_bytes_mean`
- `result_count`

## Verification

Run the registered focused `test_command`, `coverage_command`, and
`probe_command` locally on Linux. The runtime effect is Python-only and locally
measurable; no Swift runtime validation is required for this slice.
