# Runtime Export Diagnostic Marker Fast Path

## Scope

This slice keeps the runtime export diagnostic parser behavior unchanged while reducing regex work on noisy progress lines.

Affected registered probe:

- `runtime-export-diagnostic-parser` in `infra/perf/pr_scoped_probes.json`

## Change

- Narrow the `runtime_load_failed` diagnosis marker prefilter from broad single tokens (`load`, `failed`, etc.) to phrases that still cover every registered runtime-load expression.
- Reuse a precomputed known-diagnosis-code set for report coverage checks instead of rebuilding a temporary set during each metrics report.

## Verification

Linux-local verification for this Python slice must include:

- focused diagnostic parser tests
- changed-scope coverage through the registered probe coverage command
- the registered `runtime-export-diagnostic-parser` probe command

## Expected Effect

No receipt schema or diagnostic matching behavior changes. The expected performance effect is lower `diagnosis_matching_elapsed_ms_mean` for progress-heavy excerpts where lines contain broad words such as `loaded` and `failure` but do not contain a runtime-load failure phrase.

## Follow-up: Runtime-load Marker Priority

The 2026-08-09 follow-up keeps the same registered probe and narrows only to
`_has_diagnosis_marker(...)`. Runtime-load phrases are now checked before the
rarer architecture/blob/binary/path/memory markers because the registered probe's
noisy matching fixture repeatedly contains `runtime load failed`. The boolean
prefilter result is unchanged; the slice only reduces substring probes on common
runtime-load lines before the exact/fast-phrase diagnosis table runs.
