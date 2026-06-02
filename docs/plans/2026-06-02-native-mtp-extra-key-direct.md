# Native MTP sidecar key direct prefix check

## Scope

Optimize the Python native-MTP sidecar shard discovery path in
`services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`native-mtp-loader-safetensor-scandir` in `infra/perf/pr_scoped_probes.json`.
The probe already defines focused `test_command`, `coverage_command`, and
`probe_command` entries and measures the extra sidecar file filter path along
with the model shard listing and key prefix checks.

## Change

`extra_mtp_safetensor_files()` reads `model.safetensors.index.json` with
`json.loads()`, so `weight_map` object keys are JSON object member names and are
therefore strings. This slice keeps the public `_is_mtp_weight_key()` helper
behavior unchanged for direct callers and custom key objects, but the JSON index
hot loop now checks `key.startswith(_MTP_WEIGHT_KEY_PREFIXES)` directly instead
of routing every JSON string key through the generic helper.

This removes one Python function call and one type branch per index entry while
preserving the same filter semantics for the JSON-derived sidecar discovery
path.

## Validation plan

1. Run the focused native-MTP loader tests and PR-scoped probe registry tests.
2. Run changed-scope coverage for `mlx_lm_loader.py` through the registered
   coverage command.
3. Run the registered probe locally on Linux against `origin/main` and this
   branch.
4. Use GitHub Actions and the registered PR-scoped performance workflow as the
   final merge gate.
