# Benchmark Queue Binary Open Slice

## Scope

This performance slice keeps the benchmark queue persistence behavior unchanged while
reducing cold decode overhead for `BenchmarkQueueStore.list_records`.

## Plan

1. Preserve the existing decoded-record cache and per-call cloned return records.
2. Replace the uncached `Path(...).read_bytes()` decode path with direct binary
   `open(cache_key, "rb")` on the already normalized filesystem key.
3. Keep the `benchmark-queue-decoded-record-cache` PR-scoped probe as the source
   of local and CI performance validation.

## Verification

- Focused queue store tests cover binary decoding, metadata cache invalidation,
  and mutation isolation.
- Changed-scope coverage must include `benchmark_queue.py`, its tests, and the
  PR-scoped performance dispatch tests.
- The registered `benchmark-queue-decoded-record-cache` probe reports cold and
  warm elapsed times plus JSON load counts.

## Expected impact

The cold queue listing path avoids a transient `Path` allocation for each
uncached queue record by reading bytes directly through the cached string path.
Warm listings should remain cache-backed with zero JSON reloads.
