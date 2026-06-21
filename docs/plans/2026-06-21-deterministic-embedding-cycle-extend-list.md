# Deterministic embedding single-cycle detection scan

## Context

The registered PR-scoped probe `deterministic-embedding-duplicate-input-cache` covers
`worker/runtime/deterministic_embedding_runtime.py` and measures repeated embedding
input batches, including multi-input cycles and single-input cycles.

## Slice

For repeated single-input cycles, keep the existing duplicate-input semantics but
avoid validating the cycle by allocating one-item slices for every remaining
input. Once the repeated cycle candidate length is known to be `1`, scan the
remaining inputs by index and return immediately when all entries equal the first
input. Multi-input cycle validation remains unchanged.

## Validation

- Focused embedding runtime tests from the registered probe.
- Changed-scope coverage command from the registered probe.
- Local Linux run of `scripts/deterministic_embedding_duplicate_probe.py` before
  and after the code change.

## Known boundary

This is a Python worker optimization and is locally verifiable on Linux. No Swift
runtime effect is claimed for this slice.
