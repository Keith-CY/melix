# Training dataset chunker extend binding performance slice

This Python-only performance slice is limited to `worker.model_ops.training_dataset_chunker.chunk_long_samples()`.

## Registered PR-scoped probe

The affected path is covered by the registered PR-scoped probe `training-dataset-chunker-top-level-base-copy` in `infra/perf/pr_scoped_probes.json`. The probe watches the chunker module, focused chunker tests, PR-scoped performance tests, and `scripts/training_dataset_chunker_top_level_copy_probe.py`; it defines focused `test_command`, `coverage_command`, and `probe_command` entries.

## Slice

The hot loop over source samples now binds `chunked.extend` and `_chunk_sample` once before iteration. Behavior remains unchanged: each source sample is processed once, emitted chunks are extended into the result list, and aggregate stats still report the source and output counts.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate after the PR is opened.

## Metrics

Primary registered metrics:

- `elapsed_ms_mean` lower is better.
- `peak_bytes_mean` lower is better.

The optimization is accepted only if local and CI registered probe results do not regress and show a directionally useful latency movement for the chunking hot loop.
