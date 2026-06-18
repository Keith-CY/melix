# LoRA auxiliary module local binding slice

## Scope

Optimize exactly one Python hot path in
`services/mlx-worker-python/worker/model_ops/lora_runtime_metadata.py`:
`_aux_modules_restored`, which scans a base model directory for custom LoRA
auxiliary Python modules when building canary receipt fields.

## Registered probe

Registered PR-scoped probe: `lora-aux-modules-scandir` in
`infra/perf/pr_scoped_probes.json`.

The registry entry covers the affected LoRA runtime metadata module and includes
focused `test_command`, `coverage_command`, and `probe_command` entries. The
probe records auxiliary-module scan latency, `os.scandir` call count, peak
memory, and adjacent LoRA receipt hot-path metrics.

## Slice decision

Keep behavior unchanged and bind the auxiliary prefix tuple and `os.scandir`
lookup once before the directory-entry loop. This avoids repeated global/module
lookups while preserving the existing single-`scandir` traversal and `OSError`
fallback behavior.

## Verification expectation

Before merge, run the focused registry tests, changed-scope coverage command,
and registered probe locally on Linux. The PR-scoped performance workflow must
also complete successfully on GitHub Actions before merging.
