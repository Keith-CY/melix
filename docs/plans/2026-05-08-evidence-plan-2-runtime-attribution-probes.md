# Plan 2: Runtime Attribution And Stage Probes

## Goal

Make every material Melix run explainable by component and phase.

## Scope

- Add structured probes across CLI, control plane, worker, runtime, adapter,
  cache, telemetry, and report generation.
- Record runtime attribution for each run.
- Attach cache, fallback, speculative decode, and DFlash diagnostics to the
  relevant probe phases.

## Implementation Notes

- Use the probe fields and phase names from
  `docs/evidence-telemetry-report-contract.md`.
- Record worker id, runtime kind, runtime process hint, model snapshot, adapter
  id, cache profile, and fallback state in the evidence envelope.
- Write probes directly to the evidence artifact; do not reconstruct them from
  logs after the run.
- Keep probe attributes small and scrubbed of full prompts, responses, dataset
  rows, credentials, and secrets.

## Implementation Status

- Serving benchmark and evaluation evidence now write root `worker_dispatch`,
  `runtime_prepare`, `adapter_load`, row/sample stage, and `artifact_write`
  probes directly into `run-evidence.json`.
- Benchmark probes are derived from persisted context and batch rows so
  `dataset_materialize`, `prompt_render`, `cache_lookup`, `cache_restore`,
  `prefill`, `decode`, and `fallback_enter` phases remain attached to the run
  evidence artifact.
- Evaluation probes are derived from persisted sample records with bounded
  cardinality. Evidence writes aggregate summary probes for every evaluation
  phase and only expands a configurable representative sample set covering
  slowest top-N, failed, skipped, and fallback samples. This preserves phase
  attribution without scaling probe timeline size linearly with suite sample
  count.
- Benchmark persistence now owns the context and batch JSONL artifacts used for
  probe generation, keeping artifact writes and probe evidence in one store
  transaction.
- Benchmark/evaluation comparison reports summarize run-evidence probes and
  export probe-derived metrics for slowest phases, failed phases, skipped
  phases, and fallback phases.
- The evaluation-store CSV streaming performance probe pins representative
  sample detail to a minimal configured bound so it continues measuring CSV
  streaming overhead rather than diagnostic probe sample expansion.
- Apple Silicon hardware, process, and power probes remain in Plan 3; this plan
  keeps the existing explicit telemetry gap instead of synthesizing hardware
  values.

## Verification

- Unit tests for probe serialization and parent/child span relationships.
- Integration fixture proving a slow run can be localized to queue, dataset,
  prompt render, adapter load, cache restore, prefill, decode, or report export.
- Fixture coverage for adapter on/off, cache hit/miss, provider fallback, and
  failed phase probes.

## Acceptance

- Every new benchmark and evaluation evidence artifact contains a probe
  timeline.
- Report generation can summarize slowest phases, failed phases, skipped phases,
  and fallback phases.
- Release evidence can point to the responsible component for a regression.
- Large evaluation runs keep probe timeline memory and artifact size bounded by
  the configured representative sample limit instead of the raw sample count.
