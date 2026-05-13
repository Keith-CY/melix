# Bench Eval Batch Run Productization

## Goal

Productize operator benchmark plus evaluation batch runs: support dry-run
planning, non-dry-run per-model execution, durable manifests, status
inspection, resume/missing-only workflows, failure attribution, and
operator-visible summary bundles.

## Governing Issues

This slice advances the full `[Bench/Eval]` issue tree rooted at #745:

- #746 Define the canonical batch run contract and artifact shape
- #770 Define manifest schema and status lifecycle
- #756 Implement file-driven model list ingestion
- #758 Add effective configuration resolver
- #759 Add per-model staging directory layout
- #775 Define resume and subset selection contract
- #768 Add terminal progress summary format
- #850 Document the batch-run operator quickstart
- #755-#768 Execute per-model benchmark/evaluation/export pipelines
- #769-#792 Persist manifests, status, recovery, and resume
- #793-#816 Gate runtime health, classify failures, and record isolation policy
- #817-#836 Produce report/evidence bundles and load mixed-status fixtures
- #837-#852 Improve terminal progress, actionable failures, and config visibility

## Scope

- Extend `docs/benchmark-evaluation-contract.md` with combined batch-run
  planning semantics.
- Add a written plan for the foundation slice.
- Add a new `melix batch run` CLI command surface.
- Support `--dry-run` planning and non-dry-run execution.
- Parse text model lists while preserving duplicate entries.
- Support explicit `index|repo_id` model entries and auto-indexed repo-only
  entries.
- Resolve effective configuration from CLI options, config file values,
  environment variables, and Melix defaults.
- Support subset planning through `--start-index` and `--max-models`, where
  `--start-index` is a 1-based model-list position independent of display
  model indexes.
- Write `effective-config.json`, `manifest.jsonl`, `RUN_SUMMARY.md`,
  `run-summary.json`, `run-summary.csv`, and `index.html` to operator-visible
  roots.
- Print compact terminal progress for dry-run, execution, status, and resume.
- Add `melix batch status` and `melix batch resume`.
- Cover parser, runner, manifest, report, status, partial failure, and resume
  behavior with targeted Swift tests.

## Non-Goals

- Adding a Window UI surface.
- Replacing canonical `bench` or `eval` semantics.
- Embedding raw judge/provider secrets in batch configs or artifacts.

## Architecture

The CLI owns the batch orchestration surface. It does not create new benchmark
or evaluation semantics; it dispatches existing `bench` and `eval` commands and
records their outputs in a batch manifest.

`BatchRunPlanner` builds an immutable `BatchRunPlan` by resolving:

- model list path
- run id
- temporary and output roots
- subset controls
- judge server and model
- benchmark suite controls
- evaluation suite controls
- failure-continuation behavior
- per-model stack restart behavior

`BatchRunArtifacts` writes two planning artifacts:

- `effective-config.json`
- `manifest.jsonl`

`BatchRunExecutor` owns non-dry-run execution. It stages one output and
temporary directory per model, dispatches the existing CLI product commands via
the configured `melix_cli`, writes command receipts under each model directory,
updates `manifest.jsonl` incrementally, exports CSV/JSONL artifacts as soon as
job ids are known, and copies raw artifact paths into the model bundle when the
child command reports them.

`BatchRunManifestStore` is the crash-safe source of truth for status and resume.
It loads and rewrites JSONL rows without relying on summary prose.

`BatchRunReporter` writes operator-visible summary artifacts:

- `RUN_SUMMARY.md`
- `run-summary.json`
- `run-summary.csv`
- `index.html`

`BatchRunResumePlanner` rebuilds a model list from the manifest when necessary
and preserves run id, artifact roots, judge, benchmark, and evaluation settings
from `effective-config.json`.

The temporary run directory remains the working source for future execution.
The operator output directory receives a copy immediately so an interrupted run
still leaves inspectable evidence outside transient worker state.

## Metrics And Success Targets

- Model-list parsing preserves duplicates and records source line numbers.
- Dry-run planning writes one manifest row per selected model.
- `effective-config.json` records selected and total model counts.
- Subset selection is deterministic for `--start-index` and `--max-models`.
- Dry-run command completion does not require a running Melix development
  stack, network access, or local model downloads.
- Non-dry-run execution updates manifest status after every stage.
- Each dispatched command records stdout, stderr, duration, and a JSON receipt.
- Summary artifacts are present in `output_root` after completion or resume.
- Status inspection reads `manifest.jsonl` directly.
- Resume eval-only reruns missing evaluation/export work without rerunning
  benchmark stages.
- Failure classification persists both model-level and step-level category and
  recoverability.

Performance probes and success metrics:

- Manifest write overhead target: one atomic JSONL rewrite per stage, bounded by
  selected model count and acceptable for operator-scale sweeps.
- Command receipt overhead target: one stdout file, one stderr file, and one
  JSON receipt per dispatched child command.
- Progress latency target: terminal progress lines are produced at every
  model/stage boundary instead of only after the full sweep.
- Recovery target: `melix batch status` and `melix batch resume --dry-run` work
  from only `--temp-root` or only `--output-root` when the manifest exists.

## Verification

- Swift parser tests for `melix batch run`, `melix batch status`, and
  `melix batch resume` option decoding.
- Swift runner tests for dry-run artifact generation and subset selection.
- Swift runner tests for non-dry-run benchmark/evaluation/export dispatch,
  manifest updates, summary artifacts, status rendering, partial failure
  attribution, and eval-only resume.
- `git diff --check`.
- `xcrun swift build --product melix`.
- Targeted Swift test invocation for the touched CLI tests when the local Swift
  toolchain provides the `Testing` module.

## Rollout

The dry-run path remains safe for local plan inspection because it only performs
local validation and artifact writes. The non-dry-run path should be launched
with isolated `MELIX_HOME`, runtime dir, service instance, and HTTP port as
documented in `AGENTS.md`.

## Known Follow-Ups

- Add a Window UI surface if the product later needs one.
- Add richer HTML charts once stable benchmark/evaluation metric families are
  finalized.

## Issue 752 Config Schema Slice

The follow-up config-schema slice closes the remaining `melix-batch.yaml`
contract gap without expanding execution behavior.

### Scope

- Document every supported top-level `key: value` config field in
  `docs/benchmark-evaluation-contract.md`.
- Align each field with its CLI override, environment fallback, and default.
- Define the credential rule: batch configs reference stored credential records
  such as `judge_remote_server_id`; they never embed API keys or tokens.
- Reject unsupported config keys so typos do not silently disappear from the
  effective plan.
- Reject config keys that look like raw secret carriers, including
  `*_api_key`, `*_token`, `*_secret`, and `*_password`.

### Metrics And Success Targets

- The documented field set matches the current `BatchRunPlanner` resolver.
- Secret-bearing values remain represented by stored credential ids rather than
  raw key material.
- Unsupported and raw-secret-looking config keys fail before any dry-run
  artifacts are written.

### Verification

- Targeted Swift runner coverage for unsupported and secret-looking config keys.
- `git diff --check`.
- `xcrun swift build --product melix`.
