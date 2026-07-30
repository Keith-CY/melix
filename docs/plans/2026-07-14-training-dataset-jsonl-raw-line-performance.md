# Training Dataset JSONL Raw-Line Performance Slice

## Scope

Optimize the Python training dataset package JSONL row reader in
`services/mlx-worker-python/worker/model_ops/training_dataset.py`.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`Training dataset validation sample-limit loading` in
`infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- `services/mlx-worker-python/tests/test_training_dataset_builder.py`
- `scripts/training_dataset_validation_limit_probe.py`

## Optimization

Keep the row reader's whitespace-only line skip behavior, but avoid allocating a
stripped copy of every non-empty JSONL row. The hot path now uses
`raw_line.isspace()` to identify blank/whitespace-only rows and passes the
original line directly to `json.loads`, which already accepts trailing newlines
and surrounding JSON whitespace.

## Success Metrics

Use the registered probe metrics:

- `elapsed_ms_mean` lower is better,
- `peak_bytes_mean` lower is better or neutral,
- `validation_sample_count_mean` must remain `1.0` for the sample-limit fixture.

The slice is accepted only if focused tests pass, changed-scope coverage is at
least 95%, and the registered probe improves or remains non-regressive locally
and in the PR-scoped CI report.
