# PR-scoped Report Results Stat Elision

## Scope

This performance slice is limited to the PR-scoped performance report results
loader in `scripts/pr_scoped_performance_report.py`. The report path is already
covered by the registered PR-scoped probe
`pr-scoped-performance-report-results-scandir` in
`infra/perf/pr_scoped_probes.json`.

## Registered Probe

The registered probe defines focused `test_command`, `coverage_command`, and
`probe_command` entries. It measures `_load_results()` across a synthetic
directory containing 2,000 JSON result files and records:

- `elapsed_ms_mean`
- `elapsed_ms_min`

## Change

Replace the pre-scan `Path.exists()` check with a single `os.scandir()` attempt
wrapped in `OSError` handling. This keeps missing-directory behavior unchanged,
keeps deterministic sorted result loading, and avoids one extra filesystem stat
on the hot path.

While validating CI, the PR also normalizes registered probe commands from
`python` to `python3`. For checked-in script-backed `command_json` probes, the
commands invoke the script directly through `uv run ... python3` rather than a
nested shell so macOS CI keeps the project environment on the interpreter path.
This does not change probe semantics.

## Validation Plan

Run the focused registered tests, changed-scope coverage, and the registered
probe locally on Linux with `python3`. GitHub Actions remains the merge gate for
the registered PR-scoped performance report.