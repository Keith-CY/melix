# Plan 3: Apple Silicon Hardware Power Telemetry

## Goal

Add Apple Silicon hardware telemetry for Melix performance diagnosis, including
power, frequency, thermal, utilization, memory, and process attribution.

## Scope

- Build a macOS Apple Silicon telemetry collector.
- Sample hardware and process metrics off the benchmark/evaluation hot path.
- Persist run-level telemetry time series and summaries.
- Attribute process cost to Melix control plane, workers, model runtimes, and
  external providers.

## Implementation Notes

- Collect CPU utilization, P-core and E-core utilization, GPU utilization, GPU
  frequency, GPU power, CPU power, ANE power, DRAM power, system power, memory
  used and total, thermal state, process CPU, and process memory.
- Use IOReport and IORegistry where required for Apple Silicon power and GPU
  state sampling.
- Use port, pid, process tree, and bundle prefix data for process attribution.
- Run sampling on a background path and expose cached samples to benchmark and
  evaluation execution.
- Record telemetry failures explicitly with probes and report fields. Do not
  synthesize zero values for missing samples.

## Implementation Status

- Added a single macOS Apple Silicon telemetry collector path under the Python
  worker productization layer.
- The collector samples power, utilization, memory, thermal, and process data
  through Apple system telemetry commands and records failures explicitly when a
  hardware channel is unavailable.
- Benchmark and evaluation execution start a background telemetry session before
  run work and pass the completed telemetry collection into the evidence store.
- Benchmark and evaluation stores persist `telemetry-samples.jsonl`, attach the
  artifact to `run-evidence.json`, and include telemetry `hardware_sample`,
  `process_sample`, and `power_sample` probes.
- The telemetry summary now carries average and peak CPU/GPU/ANE/DRAM/system
  power, GPU frequency, CPU/GPU utilization, memory, process attribution,
  thermal events, watts per output token when output tokens are known, and
  explicit telemetry failures.
- Benchmark/evaluation comparison reports export telemetry-derived metrics from
  run evidence so power and process regressions can be compared alongside
  runtime probe metrics.
- The implementation does not add alternate platform collectors or public
  leaderboard/submission paths.

## Verification

- Collector smoke test on Apple Silicon macOS producing telemetry summary and
  JSONL time-series artifacts.
- Failure fixture for unavailable IOReport or IORegistry channels.
- Hot-path test proving telemetry sampling does not block stream consumption or
  evaluation row execution.
- Process-attribution test that separates control plane, worker, runtime, and
  external provider processes.

## Acceptance

- Completed runs include Apple Silicon telemetry summary and time-series paths.
- Reports include average/peak power, frequency, utilization, memory, thermal
  events, process attribution, and watts per output token.
- Telemetry failures are visible in evidence, reports, and gates.
