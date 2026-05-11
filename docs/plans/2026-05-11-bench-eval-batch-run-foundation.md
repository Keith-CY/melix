# Bench Eval Batch Run Foundation

## Goal

Add the first durable foundation for operator benchmark plus evaluation batch
runs: a documented `melix batch run --dry-run` command that normalizes model
lists, resolves effective run configuration, writes initial planning artifacts,
and prints a compact operator summary without starting any runtime work.

## Governing Issues

This slice advances the first recommended execution group:

- #746 Define the canonical batch run contract and artifact shape
- #770 Define manifest schema and status lifecycle
- #756 Implement file-driven model list ingestion
- #758 Add effective configuration resolver
- #759 Add per-model staging directory layout
- #775 Define resume and subset selection contract
- #768 Add terminal progress summary format
- #850 Document the batch-run operator quickstart

Follow-up execution, resume, health, reporting, and UX work remains tracked in
the existing sub-issues under #745, #769, #793, #817, and #837.

## Scope

- Extend `docs/benchmark-evaluation-contract.md` with combined batch-run
  planning semantics.
- Add a written plan for the foundation slice.
- Add a new `melix batch run` CLI command surface.
- Support `--dry-run` as the only executable mode in this slice.
- Parse text model lists while preserving duplicate entries.
- Support explicit `index|repo_id` model entries and auto-indexed repo-only
  entries.
- Resolve effective configuration from CLI options, config file values,
  environment variables, and Melix defaults.
- Support subset planning through `--start-index` and `--max-models`, where
  `--start-index` is a 1-based model-list position independent of display
  model indexes.
- Write `effective-config.json` and `manifest.jsonl` to both temporary and
  operator output roots.
- Print a compact terminal plan summary.
- Cover parser and runner behavior with targeted Swift tests.

## Non-Goals

- Running Hugging Face reachability checks.
- Starting or restarting Melix runtime stacks.
- Dispatching benchmark or evaluation jobs.
- Resuming partial runs from prior manifests.
- Producing final CSV, Markdown, or evidence bundles.
- Adding Window UI surfaces.

## Architecture

The CLI owns the planning surface for this foundation slice. It does not create
new benchmark or evaluation semantics; it records how existing `bench` and
`eval` work will be orchestrated in later slices.

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
- Non-dry-run execution returns a clear unsupported-mode error until the
  execution sub-issues land.

## Verification

- Swift parser test for `melix batch run --dry-run` option decoding.
- Swift runner test for dry-run artifact generation and subset selection.
- `git diff --check`.
- Targeted Swift test invocation for the touched CLI tests.

## Rollout

This command is safe to expose behind the required `--dry-run` flag because it
only performs local validation and artifact writes. Operator runbooks can begin
using it to inspect batch plans before the execution, resume, and reporting
slices are implemented.

## Known Follow-Ups

- Implement per-model hub preflight and staging directories beyond planned
  manifest paths.
- Dispatch `bench run` and `eval run` per model.
- Persist in-progress and terminal manifest status updates.
- Resume missing benchmark or evaluation work from existing manifests.
- Produce final terminal, Markdown, CSV, JSONL, and downloadable evidence
  bundles.

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
