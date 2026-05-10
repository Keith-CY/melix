# Startup Version Compare Performance Slice

## Goal

Reduce avoidable work in startup update-channel semantic version comparisons while
preserving the existing tolerant version parsing contract.

## Scope

This slice is intentionally limited to `worker.productization.startup_signals`
version parsing/comparison and its PR-scoped performance probe coverage. It does
not change update-channel schema, startup failure classification, or packaging
metadata.

## Change

- Reuse a precompiled leading-integer regex for version components instead of
  going through `re.match()` on every component.
- Compare normalized version parts in one pass with implicit zero padding instead
  of allocating padded left/right lists before each comparison.
- Register `startup-signals-version-compare-single-pass` as a PR-scoped probe
  with focused test, coverage, and probe commands.

## Metrics

Primary registered probe: `startup-signals-version-compare-single-pass`.

- `elapsed_ms_mean`: lower is better.
- `peak_bytes_mean`: informational, because peak allocation is dominated by the
  synthetic pair workload and should not gate this single-pass comparison change.
- `comparison_total`: informational checksum to keep the workload observable.

## Verification

Run the registered focused test command, coverage command, and probe command from
`infra/perf/pr_scoped_probes.json` before opening the PR. The PR-scoped
performance workflow must complete successfully before merge.
