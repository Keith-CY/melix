# Changed-scope coverage measured-set union elision

## Context

The changed-scope coverage gate is invoked by focused coverage commands and by
PR-scoped performance probes. `_measurable_changed_lines` receives the changed
line set for a file and the coverage JSON entry for that same file. For files
with many measured lines but only a few changed lines, the previous flow built
`executed | missing` before intersecting with `changed`.

## Slice

This slice keeps behavior unchanged while avoiding the extra combined measured
set allocation. The function still materializes the executed and missing lookup
sets used later for covered/missed classification, but it now filters changed
lines directly against those two lookups.

## Probe

The existing `changed-scope-coverage-empty-path-short-circuit` probe remains
registered for its original empty-path fast path. This slice adds the registered
`changed-scope-coverage-measured-set-filter` probe for the affected shape:

- many measured coverage lines per path;
- a small changed set outside the measured range;
- zero source-file reads when no changed line is measurable.

Expected direction for the measured-set probe: lower `elapsed_ms_mean`;
`source_read_calls_mean` must remain `0.0`.

## Verification

Run the focused changed-scope test set, changed-scope coverage command, and the
registered probe command from `infra/perf/pr_scoped_probes.json` before opening
the PR.
