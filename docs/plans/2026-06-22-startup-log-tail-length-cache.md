# Startup log tail scan search-window elision

## Context

`worker.productization.startup_signals._seek_last_nonempty_line_bounds(...)`
walks startup logs backward in fixed-size chunks to find the last non-empty
line used in startup failure reports. The registered PR-scoped performance
probe `startup-signals-lazy-worker-log-excerpts` already covers this path with
focused tests, coverage, and a tail-scan workload containing substantial
trailing whitespace.

## Optimization Slice

Defer computing the full chunk search window until after the trailing-whitespace
phase has found payload bytes. Whitespace-only chunks now skip the otherwise
unused `len(chunk)` dispatch and continue directly to the previous chunk. This
keeps the newline search and returned bounds unchanged while trimming a tiny
amount of overhead from long trailing-whitespace scans.

## Verification

- Focused startup-signal regression tests.
- Changed-scope coverage for `startup_signals.py`, its tests, the registered
  probe script, and the PR-scoped probe registry tests.
- Local Linux run of the registered `startup-signals-lazy-worker-log-excerpts`
  probe before and after the change.
