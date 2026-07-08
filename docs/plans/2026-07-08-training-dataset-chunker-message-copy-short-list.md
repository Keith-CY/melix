# Training Dataset Chunker Short Message Copy Fast Path

## Scope

This Python-only performance slice narrows the message-copy path in
`services/mlx-worker-python/worker/model_ops/training_dataset_chunker.py`.
The chunker emits many two-message chunks for long single-turn samples and
three-message chunks when a system prefix is present. Each emitted chunk copies
only message dictionaries before attaching shared top-level sample fields.

## Registered Probe

The affected path is already covered by the PR-scoped
`training-dataset-chunker-top-level-base-copy` command-json probe in
`infra/perf/pr_scoped_probes.json`. The registered probe includes focused
`test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/training_dataset_chunker.py`
- `services/mlx-worker-python/tests/test_training_dataset_chunker.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/training_dataset_chunker_top_level_copy_probe.py`

## Planned Optimization

Add an exact-size fast path to `_copy_messages` for the dominant two- and
three-message chunk outputs. The implementation preserves shallow message-dict
copy semantics and falls back to the generic list comprehension for all other
message counts.

## Verification

- Focused chunker tests for two-message, three-message, and independent message
  copies.
- Changed-scope coverage using the registered coverage command.
- Local Linux execution of the registered command-json probe before PR creation.
- Hosted PR-scoped performance workflow after push remains the merge gate.
