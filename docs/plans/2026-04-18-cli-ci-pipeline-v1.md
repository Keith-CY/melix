# CLI/CI Pipeline v1

## Goal

Add a pipeline-first layer to the `melix` CLI while preserving existing single-command behavior
and the current `--json` payloads.

## Implementation Slice

- Add `--format json-v1` as an additive machine contract around existing command results.
- Keep `--json` payloads unchanged for existing callers.
- Add `melix pipeline run --file PIPELINE.json` with optional inputs, receipt directory,
  trace ID, resume, from-step, dry-run, and `json-v1` output.
- Add a shared command argument codec so parser tests, pipeline execution, and the macOS
  subprocess bridge use one command-to-argv mapping.
- Persist one JSON receipt per step plus a run summary manifest under
  `MELIX_HOME/pipelines/<pipeline-name>/<trace-id>/` unless `--receipt-dir` overrides it.
- Attach `pipeline_step` metadata to step receipts, including step ID, index, command ID,
  pipeline hash, input hash, and resolved-argument hash, so resume and from-step recovery can
  reject stale or swapped receipts.
- Include step-level `artifact_paths` in the summary when command receipts expose output,
  report, bundle, managed-model, or artifact paths.
- Keep `scripts/phase8_acceptance_bundle.py` as the compatibility path during v1.

## Pipeline Contract

Pipeline files use JSON:

```json
{
  "schema_version": "melix.pipeline.v1",
  "name": "pipeline-name",
  "inputs": {},
  "steps": []
}
```

Each step has:

- `id`: unique step identifier.
- `command`: typed Melix command ID, such as `model.import`, `chat.run`, `lora.train`,
  `bench.matrix.run`, or `eval.run`.
- `args`: snake_case command arguments.
- optional `when`: `{ "input": "name", "equals": value }`.
- optional `checks`: required result fields, equality checks, and artifact path existence checks.

References use `${inputs.name}` and `${steps.step_id.result.field}`. Array indices are addressed
as path components, for example `${steps.run_evaluation.result.0.job.job_id}`.

Dry-run planning resolves input references and any step references whose receipts have already been
loaded. References to future steps remain literal `${steps...}` strings in planned command
arguments so CI can inspect the intended argv without executing upstream commands.

Pipeline documents are strict JSON objects in v1. If present, `inputs`, step `args`, `when`, and
`checks` must be JSON objects. Typed command arguments fail fast when booleans, integers, unsigned
integer arrays, or string arrays have incompatible JSON types or invalid string values.

## Verification Plan

- Parser tests cover `--format json-v1`, `pipeline run`, and command codec round-trip behavior.
- Runner tests cover `json-v1` output/error envelopes and pipeline dry-run receipt persistence.
- Pipeline tests use deterministic stubs and fixtures by default so CI failures isolate pipeline
  planning, reference resolution, receipt writing, resume, and summary behavior rather than live
  model availability.
- Resume tests reject changed pipeline/input hashes and stale step receipts. From-step tests verify
  prior receipt loading, requested-step reruns, and failed summary persistence for unknown targets.
- Existing Phase 8 acceptance script tests remain in place until the pipeline path is promoted.
- Required live model and live runtime evidence remains available through explicit opt-in gates,
  including `MELIX_PHASE8_REAL_SMALL_MODEL_E2E=1` for the real Phase 8 small-model path and
  `MELIX_RUN_LIVE_RUNTIME_TESTS=1` for CLI smoke tests that depend on local worker sockets.
- Deterministic integration coverage should pass before making the pipeline runner the default
  Phase 8 acceptance path; live evidence validates the runtime stack separately.

## Metrics

The v1 CLI/pipeline contracts expose these metric keys:

- `melix.cli.parse_ms`
- `melix.cli.command_ms`
- `melix.cli.json_encode_ms`
- `melix.pipeline.total_ms`
- `melix.pipeline.step_ms.<step_id>`
- `melix.pipeline.reference_resolve_ms`
- `melix.pipeline.receipt_write_ms`
- `melix.pipeline.resume_skipped_count`
- `melix.pipeline.failed_step_count` (fail-fast v1 semantics: `0` for no failure, `1` after the
  first failed step or preflight validation failure)
