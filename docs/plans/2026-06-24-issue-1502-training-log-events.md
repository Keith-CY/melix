# Issue 1502 Training Log Events

## Goal

Implement the first executable slice of issue #1502 by turning LoRA training
log lines into a typed, bounded event stream that can be written into adapter
manifests and later consumed by CLI, Desktop, and diagnostics surfaces.

## Governing Context

- `docs/reference-scans/m-courtyard-lessons.md`
- `docs/plans/2026-05-24-m-courtyard-improvement-roadmap.md`
- Issue #1502, U2.2.1: parse training logs into structured run events.

## Scope

- Add a deterministic Python parser for training log lines.
- Emit typed rows for progress, loss, validation loss, final summary, OOM,
  Metal watchdog, stalled progress, and rising loss.
- Emit alert rows with severity, operator message, and redacted evidence
  pointers.
- Add parser counters for parsed rows, unparsed lines, parser errors, and
  parse duration.
- Store a compact parser summary and bounded event preview in LoRA adapter
  manifests.

## Non-Goals

- Real-time Desktop training monitor UI.
- New protobuf schema fields.
- Changes to MLX-LM training behavior.
- Blocking training when parsing fails.

## Architecture

The best end state is a single model-ops parser contract that reads raw trainer
output and yields machine-readable rows independent of how training is
executed. The parser should be pure and deterministic so it can run on captured
subprocess stdout/stderr, future streaming logs, or persisted log files without
touching worker runtime state.

This slice keeps the implementation small:

- `worker.model_ops.training_log_events` owns event and summary shapes.
- `TrainingMetrics` carries parsed event rows from the runner to the LoRA
  pipeline.
- `LoRATrainingPipeline` writes a bounded manifest projection so existing
  adapter history and diagnostics can read structured run state without parsing
  logs again.

## Performance Probes And Metrics

Measurement points:

- Parser wall-clock duration while scanning lines.
- Input line count.
- Parsed event row count.
- Alert row count.
- Unparsed line count.
- Parser error count.

Success metrics for this slice:

- Fixture parse duration remains below 50 ms.
- Parser failures are reported in counters and do not raise from pipeline
  manifest generation.
- Manifest event preview stays bounded by a configured event limit.

## Verification

- Focused parser fixture tests for every required event type.
- Pipeline manifest test proving the summary and preview are persisted.
- Changed-scope coverage for touched Python files.
- `git diff --check`.
