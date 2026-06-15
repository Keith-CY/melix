# LoRA auxiliary module prefix filter slice

## Scope

This Python performance slice is limited to `services/mlx-worker-python/worker/model_ops/lora_runtime_metadata.py` and the LoRA canary auxiliary-module scan used while building LoRA training receipts.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `lora-aux-modules-scandir` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for the LoRA runtime metadata module, receipt tests, PR-scoped performance tests, and `scripts/lora_aux_modules_scandir_probe.py`.

## Change

The auxiliary module detector already uses a single `os.scandir` pass and preserves `modeling_*.py`, `configuration_*.py`, `tokenization_*.py`, and `processing_*.py` semantics. This slice adds a precomputed first-character filter before the `.py` suffix and tuple-prefix checks so large base model directories with unrelated files can reject common non-candidate names with a cheaper membership check.

## Verification Plan

- Run the registered focused test command for `lora-aux-modules-scandir` locally on Linux.
- Run the registered changed-scope coverage command locally on Linux and require at least 95% changed-scope coverage.
- Run the registered probe locally on Linux and compare against `origin/main` with the PR-scoped performance runner.
- Use GitHub Actions, including the registered PR-scoped performance report, as the merge gate before squash merging.
