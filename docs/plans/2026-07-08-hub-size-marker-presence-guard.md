# Hub catalog size marker presence guard performance slice

## Scope

This Python-only performance slice is limited to Hub catalog size-hint marker
screening in `services/mlx-worker-python/worker/model_ops/hub_catalog.py`.
The changed helper is `_may_contain_model_marker(...)`, which is called before
running explicit size-hint parsing for `description`, `readme`, and
`cardData.description` text fields.

## Registered probe

The affected path is already covered by the registered PR-scoped performance
probe `hub-catalog-size-hint-regex-precompile` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries and the probe
reports `elapsed_ms_mean` for the size-hint workload.

## Implementation plan

1. Preserve the existing case-insensitive two-character marker behavior for
   `MO`, `Mo`, `mo`, and `mO` sequences.
2. Add cheap single-character presence guards for both `m/M` and `o/O` so
   marker-free text exits before the four pair scans used by the existing helper.
3. Keep the existing focused Hub catalog tests as behavior parity coverage.
4. Run the registered focused tests, changed-scope coverage, and local Linux
   size-hint probe before pushing. CI remains the merge gate for the registered
   PR-scoped performance report.

## Acceptance criteria

- Focused Hub catalog and PR-scoped performance tests pass.
- Changed-scope coverage for `hub_catalog.py`, related tests, registry test, and
  the size-hint probe meets the repository threshold.
- The local registered probe shows a neutral-to-improved `elapsed_ms_mean`
  versus the same-worktree `origin/main` baseline, especially for marker-free
  `m/M`-only text that cannot contain a `mo` marker.
- The PR-scoped performance workflow completes successfully before merge.
