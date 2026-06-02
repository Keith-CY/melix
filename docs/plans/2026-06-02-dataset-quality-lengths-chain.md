# Dataset quality output length chain

## Scope

This Python performance slice is limited to dataset quality summary output-length aggregation in `services/mlx-worker-python/worker/productization/dataset_preparation.py`.

## Probe registration

The slice adds a PR-scoped performance probe for `scripts/dataset_quality_lengths_probe.py` before claiming performance validation. The probe exercises `_quality_summary(...)` with a large synthetic train/validation row set and reports elapsed latency plus row/output-length sanity metrics.

## Behavior contract

- Dataset quality summary schema and quality metrics remain unchanged.
- `mean_output_length` and `p95_output_length` must match the existing deterministic row-length semantics for prompt/completion and chat-message rows.
- The optimization must avoid unrelated dataset ingest/listing behavior changes.

## Verification plan

- Focused dataset versioning tests for quality summary behavior.
- PR-scoped performance registry tests for probe selection and metric emission.
- Changed-scope coverage for the touched Python module, tests, registry, and probe script.
- Registered probe locally on Linux, then PR-scoped performance CI before merge.
