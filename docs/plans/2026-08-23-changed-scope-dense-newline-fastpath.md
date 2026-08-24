# Changed-scope dense newline fast path

## Scope

This Python-only performance slice is limited to `scripts/changed_scope_coverage.py` dense source-line measurement in `_measurable_non_comment_lines()`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `changed-scope-coverage-measured-set-filter` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches `scripts/changed_scope_coverage.py`, `scripts/changed_scope_coverage_measured_probe.py`, `tests/test_changed_scope_coverage.py`, and the probe registry.

## Optimization

Dense changed-line measurement must preserve diff-parser line numbering for universal newlines, including bare `\r`. `Path.read_text()` already uses Python universal-newline handling, so the dense path can split the loaded text on `\n` directly. This removes two full-string `replace()` passes from the LF-only hot path while preserving the existing CR/CRLF behavior covered by regression tests.

## Verification plan

1. Run the focused changed-scope coverage tests and PR-scoped registry tests.
2. Run changed-scope coverage for the touched tool, probe, tests, registry, and this plan.
3. Run the registered local probe on Linux before pushing.
4. Use the PR-scoped performance workflow as the merge gate for the registered CI probe report.
