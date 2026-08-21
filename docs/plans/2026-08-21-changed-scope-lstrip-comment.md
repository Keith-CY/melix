# Changed-scope coverage comment trim fast path

## Scope

This Python-only performance slice is limited to
`scripts/changed_scope_coverage.py`, specifically the dense source-line scan in
`_measurable_non_comment_lines(...)`.

## Probe Coverage

The affected path is covered by the registered PR-scoped performance probe
`changed-scope-coverage-measured-set-filter` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for changed-scope
coverage behavior, changed-scope coverage reporting, and the measured-line probe,
so no new probe registration is required.

## Plan

1. Preserve measurable-line semantics: blank lines and left-indented comments are
not measurable; code lines remain measurable, including code with trailing
whitespace.
2. In the dense scan path, use `lstrip()` rather than `strip()` before the
comment check because only leading whitespace affects whether the first
significant character is `#`.
3. Run the registered focused test command, changed-scope coverage command, and
registered probe locally on Linux.
4. Use GitHub Actions PR-scoped performance as the final merge gate.

## Success Criteria

- Focused changed-scope tests and changed-scope coverage pass.
- The registered local Linux probe is neutral-to-improved for
`dense_elapsed_ms_mean` while preserving measured line counts.
- PR-scoped performance CI completes successfully before merge.
