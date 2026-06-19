# LoRA Run Directory No-Symlink-Follow Scan Performance

This Python-only performance slice is limited to the LoRA experiment run
directory scanner in `worker.productization.lora_experiment_store._iter_lora_run_dirs`.

Registered PR-scoped probe: `lora-experiment-run-dir-name-scan` in
`infra/perf/pr_scoped_probes.json`. The affected path already has focused
`test_command`, `coverage_command`, and `probe_command` entries.

## Optimization

When filtering `model-ops-*` entries, call `DirEntry.is_dir(follow_symlinks=False)`
instead of the default symlink-following directory check. The scanner only needs
real run directories under the train root, so avoiding symlink following keeps the
hot scan deterministic and removes unnecessary filesystem resolution work on
symlink-heavy roots.

## Verification Plan

Run the registered focused test command, changed-scope coverage command, and
registered probe locally on Linux. Accept this slice only if behavior tests pass,
changed-scope coverage remains at or above the repository threshold, and the
registered probe completes without elapsed or allocation regression.