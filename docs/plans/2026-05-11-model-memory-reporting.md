# Model Memory Reporting In Benchmark And Evaluation Evidence

## Summary

Benchmark and evaluation reports must expose the model memory residency that
Melix already tracks when a model is loaded into the worker registry. The report
must not reuse process telemetry, host memory telemetry, or benchmark
`peak_memory_bytes` as if those fields were model-weight residency.

## Behavior

- `run-evidence.json` records a top-level `model_memory_summary` object for
  benchmark and evaluation runs.
- `model_memory_summary` includes the loaded model handle, model id, runtime
  kind, and the registry-reported model residency after the run resolves its
  model.
- `model_memory_summary.loaded_model_estimated_resident_bytes` records the
  selected loaded model handle's resident estimate.
- `model_memory_summary.runtime_stats_model_resident_bytes` records
  `WorkerRegistry.runtime_stats().model_resident_bytes`, which is the total
  model-resident accounting for loaded models in that worker.
- `model_memory_summary.load_rss_delta_bytes` records the current worker
  process RSS increase only when the run itself triggered a lazy model load.
  Preloaded-handle runs leave this value absent or zero and rely on the registry
  model-resident fields.
- Derived comparison reports render model memory summaries in Markdown and CSV.

## Measurement Notes

Registry resident bytes are Melix's model-level accounting source of truth. The
worker RSS delta is a diagnostic approximation for the process impact of a lazy
load, and can include allocator, runtime, and framework overhead. Host
`memory_used_bytes`, process telemetry peaks, and benchmark `peak_memory_bytes`
remain separate telemetry and runtime-probe signals.

## Verification

- Python unit tests prove benchmark/evaluation run evidence round-trips
  `model_memory_summary`.
- Python unit tests prove benchmark and evaluation stores persist the summary.
- Python unit tests prove comparison reports include model memory rows in
  Markdown and CSV exports.
- `make py-test` or a focused pytest subset covering the changed modules.

## Metrics

- Coverage: changed Python modules remain covered by focused unit tests.
- Performance: memory summary collection is O(1) against
  `WorkerRegistry.runtime_stats()` and does not scan loaded model collections.
