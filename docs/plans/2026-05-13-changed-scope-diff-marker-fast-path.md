# Changed-scope coverage diff marker fast path

## Context

The changed-scope coverage helper parses `git diff --unified=0` output in PR
and local evidence flows. Its parser already dispatches on the first character of
each diff line to avoid repeated prefix checks on hot context/addition/deletion
lines.

## Slice

Treat any diff control line whose first character is `\` as the synthetic
"No newline at end of file" marker after the parser has entered a hunk. This
removes an extra `startswith("\\ ")` call from the hot parser loop while keeping
normal source lines safe: context lines that contain a literal leading backslash
still arrive from git with a leading space, and added/deleted source lines still
arrive with `+` or `-`.

## Probe and success metric

Registered PR-scoped probe: `changed-scope-coverage-diff-parser` in
`infra/perf/pr_scoped_probes.json`.

Success metric: `elapsed_ms_mean` from `scripts/changed_scope_coverage_parse_probe.py`
should decrease or remain within the probe tolerance while parser behavior tests
continue to pass.

## Verification plan

- Run focused changed-scope parser tests.
- Run the registered coverage command for the changed scope.
- Run the registered `changed-scope-coverage-diff-parser` probe locally on Linux
  before opening the PR.
