# Serving diagnostics append local fast path

## Scope

This slice keeps the registered `serving-diagnostics-debug-queue-bounds` PR-scoped probe focused on `worker/productization/serving_diagnostics.py` and the bounded debug-event queue hot path.

## Change

The bounded diagnostics queue already keeps an explicit retained-event counter to avoid calling `len(_events)` while debug events are appended. This slice narrows the non-saturated append path so `_is_saturated` is written only once, when the retained count first reaches capacity. The saturated path remains unchanged semantically: it appends to the bounded deque, increments `dropped_count`, returns `False`, and keeps the newest retained events.

## Verification

Run the registered probe locally on Linux before opening the PR, then rely on the PR-scoped performance workflow for CI validation. The expected signal is lower `elapsed_ms_mean` for `serving-diagnostics-debug-queue-bounds` while retaining identical `dropped_count`, `retained_count`, serialization checksum, and serialized byte metrics.
