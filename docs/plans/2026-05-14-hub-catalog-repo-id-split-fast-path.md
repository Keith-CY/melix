# Hub catalog repo ID split fast path

## Scope

This Python performance slice is limited to the Hub catalog summary-record path:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `infra/perf/pr_scoped_probes.json`
- existing focused tests under `services/mlx-worker-python/tests/`
- existing registered probe `hub-catalog-tag-normalization-single-pass`

## Registered probe

The affected path is already covered by the PR-scoped registered probe
`hub-catalog-tag-normalization-single-pass`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries. This slice also
keeps the probe invocation aligned with the repository cron constraint by using
`python3` in the command fallback.

## Change

Hub catalog summary construction derives `model_name` and fallback `author` from
repository IDs for every catalog record. The previous helpers checked for `/`
and then called `split("/", 1)`, which scans enough to build an intermediate list.
This slice uses a single `find("/")` result and direct slicing instead, preserving
the same behavior while reducing per-record allocation in catalog scans.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and the
registered probe locally on Linux. Compare the local probe against the pre-change
baseline and rely on the PR-scoped performance workflow for CI validation before
merge.

## Acceptance

- Focused Hub catalog tests pass.
- Changed-scope coverage for the touched Hub catalog/probe scope remains at or
  above the repository threshold.
- The registered probe remains behavior-compatible and shows stable or improved
  allocation/latency metrics versus the local baseline.
