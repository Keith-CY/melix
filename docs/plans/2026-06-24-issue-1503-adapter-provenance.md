# Issue 1503 Adapter Provenance

## Goal

Implement the first executable slice of issue #1503 by writing a schema-backed
adapter provenance manifest for completed LoRA adapters, preserving mutable
operator notes separately, and making experiment history/index payloads derive
comparison and export state from that provenance contract.

## Governing Context

- `docs/reference-scans/m-courtyard-lessons.md`
- `docs/plans/2026-05-24-m-courtyard-improvement-roadmap.md`
- Issue #1503, U2.2.2: persist adapter provenance, loss series, and notes.

## Scope

- Add a `melix.lora_adapter_provenance.v1` JSON manifest beside
  `train_lora.adapter.json` for completed adapters.
- Record immutable adapter provenance: base model identity, dataset version,
  sample counts, training hyperparameters, loss series, final metrics, artifact
  paths, canary receipts, and export eligibility.
- Store operator notes in a separate mutable
  `melix.lora_adapter_operator_notes.v1` JSON file referenced by the provenance
  manifest.
- Preserve existing adapter package manifests for backward compatibility while
  adding pointers and write metrics to them.
- Make LoRA experiment run and group index payloads prefer provenance fields for
  history/comparison/export projections when the manifest exists.

## Non-Goals

- Desktop note editing UI.
- New protobuf fields.
- Runtime export execution or post-export smoke tests.
- Re-parsing raw training logs after #1502 has already produced structured
  training events.

## Architecture

The best end state is a single provenance contract owned by model
productization and consumed by history, comparison, export, publish, and report
flows. Adapter package manifests remain the low-level artifact receipt; the
provenance manifest becomes the stable product-facing summary.

This slice keeps the boundary small:

- `worker.productization.lora_adapter_provenance` owns schema construction,
  export-eligibility computation, loss-series projection, and mutable notes
  persistence.
- `LoRATrainingPipeline` writes the provenance and notes files after the adapter
  package manifest payload is assembled and before the experiment run record is
  persisted.
- `LoraExperimentStore` loads provenance by explicit path or sibling default
  path, then derives history and comparison fields from provenance instead of
  ad hoc package-manifest keys.

Operator notes are intentionally outside immutable provenance. The provenance
manifest records the notes schema and path; note contents can change without
rewriting base model, dataset, hyperparameter, or metric provenance.

## Performance Probes And Metrics

Measurement points:

- Adapter provenance manifest write duration.
- Operator notes write duration.
- Loss-series row count.
- Provenance manifest byte size.
- Experiment comparison/index provenance load duration, measured during probes
  without writing volatile timing fields into the deterministic index payload.

Success metrics for this slice:

- Provenance and initial notes writes stay below 50 ms in focused fixtures.
- Loss series is derived from bounded #1502 structured event previews and does
  not re-read raw logs.
- Experiment index rebuild remains deterministic while comparison/index load
  latency remains measurable outside the persisted payload.
- Export eligibility is computed from manifest fields and returns explicit
  blocking reasons when required adapter artifacts or receipts are missing.

## Verification

- Focused provenance schema tests for loss-series projection, export
  eligibility, and notes immutability.
- Pipeline manifest test proving provenance and notes files are written for a
  completed adapter.
- Experiment store tests proving history/group projections prefer provenance
  fields.
- Changed-scope coverage for touched Python files.
- `git diff --check`.
