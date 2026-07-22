# PR-scoped command summary strip fast path

## Scope

This Python-only performance slice is limited to
`worker.productization.pr_scoped_performance._summarize_command()` and the
registered PR-scoped performance probe metadata for the same path.

The PR-scoped performance runner summarizes every focused command that it emits
into reports. Multiline commands are common because several registered probes use
inline shell or Python snippets. The previous implementation trimmed leading and
trailing whitespace with two full string scans (`lstrip().rstrip()`). This slice
keeps the exact summary semantics while using the single-pass built-in
`strip()` helper.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`pr-scoped-performance-scope-matcher` in `infra/perf/pr_scoped_probes.json`.
The probe already exercises `_summarize_command()` for a multiline command
payload. This slice adds `command_summary_ms_mean` to the probe's registered
metrics so CI explicitly reports the optimized subpath alongside the existing
scope-selection metrics.

The probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries and watches:

- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Verification plan

1. Run the registered focused test command.
2. Run the registered changed-scope coverage command.
3. Run the registered probe locally on Linux before and after the change.
4. Use GitHub Actions PR-scoped performance as the merge gate after opening the
   PR.

## Expected metrics

Expected direction is lower `command_summary_ms_mean` with unchanged
`selected_probe_count_mean` and `force_all_selected_mean`. `build_scope_report`
metrics may be noise-dominated because this slice only changes command summary
formatting, not scope matching semantics.
