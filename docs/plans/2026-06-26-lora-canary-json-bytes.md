# LoRA canary JSON byte-read slice

## Scope

This Python-only performance slice is limited to `worker.model_ops.lora_runtime_metadata._load_json_mapping(...)`, which reads small LoRA canary JSON sidecars such as `tokenizer_config.json` and `adapter_config.json` while building training/merge canary receipts.

The behavior contract stays unchanged: missing files, malformed JSON, and non-mapping JSON values still produce an empty mapping; valid JSON objects continue to be returned as mappings. The slice only avoids the intermediate text decoding allocation by loading JSON from `Path.read_bytes()` directly.

## Registered probe

The affected path is covered by the registered PR-scoped probe `lora-aux-modules-scandir` in `infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/lora_runtime_metadata.py`
- `services/mlx-worker-python/tests/test_lora_training_receipts.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/lora_aux_modules_scandir_probe.py`

This slice updates the focused command coverage with a direct regression test for the binary JSON read path.

## Plan

1. Add a regression test proving `_load_json_mapping(...)` reads JSON bytes without calling `Path.read_text(...)`.
2. Replace the text read with `Path.read_bytes()` while keeping the existing `json.loads(...)` parse and error handling semantics.
3. Run the registered focused test command, changed-scope coverage command, and PR-scoped performance probe locally on Linux.
4. Use GitHub Actions PR-scoped performance as the merge gate.

## Success criteria

- Focused LoRA tests and PR-scoped registry tests pass.
- Changed-scope coverage remains at or above the repository threshold for touched files.
- The registered probe reports non-regression or improvement for the LoRA auxiliary module metrics.
