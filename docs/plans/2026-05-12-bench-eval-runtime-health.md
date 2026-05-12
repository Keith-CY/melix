# Bench Eval Runtime Health

## Goal

Add the batch-run runtime health contract for #793 without taking over the
separate per-model execution work tracked by #760.

## Scope

- Add `melix batch run --dry-run --preflight`.
- Resolve and expose isolated `MELIX_HOME`, runtime dir, HTTP port, service
  instance, repo root, and CLI artifact path in the effective config.
- Write `preflight-report.json` beside the dry-run manifest and copy it to the
  operator output root.
- Block before long-run execution when required health prerequisites are
  missing.
- Add stable failure categories and recoverability values for future manifest
  updates and reports.
- Persist the default isolation policy in `effective-config.json`.

## Non-Goals

- Dispatching `bench run` or `eval run` per model.
- Restarting local stacks inside the CLI batch runner.
- Exporting CSV/Markdown/HTML summary bundles.
- Closing resume/status/reporting issues that consume the manifest later.

## Verification

- Parser coverage for `--preflight`.
- Runner coverage for ready and blocked preflight reports.
- Classifier coverage for worker connectivity, runtime unavailable, Metal OOM,
  target resolution, model load, judge failure, artifact export, and unknown
  failures.
- Targeted Swift tests for the touched CLI test suite.
