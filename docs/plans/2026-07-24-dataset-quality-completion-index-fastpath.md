# Dataset quality completion index fast-path performance slice

## Scope

This Python-only performance slice is limited to `_append_rows_output_lengths()` in
`services/mlx-worker-python/worker/productization/dataset_preparation.py`.
The behavior stays unchanged for prompt/completion rows, chat-message rows,
non-list `messages`, non-string completion/content values, and mixed row lists.

## Registered probe

The affected path is covered by the existing PR-scoped registered probe
`dataset-quality-lengths-chain` in `infra/perf/pr_scoped_probes.json`. The probe
already declares focused `test_command`, `coverage_command`, and `probe_command`
entries, and reports output-length summary timing plus failed-segment partition
metrics.

## Optimization

`_append_rows_output_lengths()` now samples the first row with the existing
sentinel `get()` path. When the row batch is completion-shaped, the hot loop uses
direct `row["completion"]` access and falls back to the existing message logic only
for mixed rows missing the key. Message-shaped batches keep the prior `get()` path
so they do not pay exception overhead or change the existing message-row guard.

This matches the production call shape where train and validation rows are passed
as separate lists; prompt/completion train rows can avoid repeated sentinel lookup
while validation chat-message rows keep the message-specific fast path.

## Verification plan

Run the registered probe's focused tests, changed-scope coverage, and local Linux
probe before opening the PR. CI PR-scoped performance remains the merge gate for
the registered probe report.
