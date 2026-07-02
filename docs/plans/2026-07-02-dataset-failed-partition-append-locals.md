# Dataset Failed Segment Partition Append Locals

## Context

The dataset versioning hot path partitions generated source segments into
successful and failed groups when `fail_segment_ids` is provided. The affected
code path is covered by the registered PR-scoped performance probe
`dataset-quality-lengths-chain` in `infra/perf/pr_scoped_probes.json`, including
focused `test_command`, `coverage_command`, and `probe_command` entries. The
probe emits `failed_partition_elapsed_ms_*` metrics for
`_partition_failed_segments`.

## Slice

Keep the behavior and data model unchanged while reducing repeated attribute
lookups in `_partition_failed_segments`:

- keep the existing empty-failures fast path that returns the original segment
  list unchanged;
- use direct `segment["segment_id"]` lookup on the common path while retaining
  missing-key behavior through a `KeyError` fallback;
- bind the result-list append methods once before the hot loop;
- keep missing segment identifiers in the successful partition instead of raising.

## Verification

Run the registered focused tests, changed-scope coverage command, and registered
probe locally on Linux before pushing. Compare the registered probe metrics
against an `origin/main` baseline gathered from the same worktree before the
slice.
