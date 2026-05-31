# Hub catalog weight/config suffix fast path

## Scope

This Python-only performance slice is limited to `worker.model_ops.hub_catalog._is_weight_or_config_file`, the helper used while summarizing Hub sibling metadata for local-fit evidence.

## Registered probe

The affected source path is already covered by the registered PR-scoped probe `hub-catalog-tag-normalization-single-pass` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for `services/mlx-worker-python/worker/model_ops/hub_catalog.py`, `services/mlx-worker-python/tests/test_hub_catalog.py`, `services/mlx-worker-python/tests/test_pr_scoped_performance.py`, and `scripts/hub_catalog_tag_normalization_probe.py`.

## Optimization hypothesis

Hub sibling filenames are normally already lowercase (`config.json`, `tokenizer.json`, `.safetensors`, `.npz`, `.gguf`). The current helper lowercases every candidate filename before suffix checks. A case-sensitive fast path for the common lowercase suffixes can avoid per-file lowercase allocation while preserving the existing case-insensitive fallback for uncommon mixed-case metadata.

## Validation plan

1. Add a focused regression test that covers lowercase suffix matches, mixed-case fallback matches, and non-weight false positives.
2. Implement only the lowercase suffix fast path plus unchanged case-insensitive fallback.
3. Run the registered focused test command locally on Linux.
4. Run changed-scope coverage locally on Linux and require at least 95% for the changed scope.
5. Run the registered probe locally against this branch and compare with the pre-change baseline captured from `origin/main` in the same worktree.
6. Use PR-scoped performance CI as the final registered probe gate before merge.
