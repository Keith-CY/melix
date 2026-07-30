# Changed-scope ASCII measurable-line fast path

## Scope

This Python-only performance slice is limited to the dense changed-line source scan in `scripts/changed_scope_coverage.py`, specifically `_measurable_non_comment_lines(...)` when coverage validation needs to inspect many changed lines from an ASCII source file.

## Registered probe

The affected path is covered by the registered PR-scoped probe `changed-scope-coverage-measured-set-filter` in `infra/perf/pr_scoped_probes.json`. The probe includes focused tests, changed-scope coverage, and `scripts/changed_scope_coverage_measured_probe.py`. This slice extends the registered metrics with dense measurable-line scan latency and dense source-read call counts because those are the direct performance signal for this change.

## Optimization plan

- Preserve the sparse streaming path for small changed-line sets.
- Add a dense ASCII byte path that uses `Path.read_bytes()` plus byte-level line checks to avoid UTF-8 decoding and `Path.read_text().splitlines()` allocation for common Python source files.
- Fall back to the existing Unicode-aware text path whenever the source contains non-ASCII bytes so `str.isspace()` semantics are preserved for Unicode whitespace.
- Add regression coverage proving ASCII dense scans avoid `Path.read_text()` and Unicode whitespace behavior remains unchanged.

## Validation

Local Linux validation uses focused changed-scope tests, changed-scope coverage for the touched files, and the registered probe before pushing. GitHub Actions PR-scoped performance remains the merge gate.
