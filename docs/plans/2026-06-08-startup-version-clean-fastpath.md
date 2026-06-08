# Startup Version Clean Fast Path

## Goal

Reduce per-comparison overhead in `compare_versions(...)` for already-clean
version strings. The startup update check and PR-scoped probe feed normalized
release identifiers in the common path, so comparisons should avoid allocating
or invoking `str.strip()` unless leading or trailing whitespace is actually
present.

## Scope

- Preserve existing raw-equality and `v`-prefix equivalence fast paths.
- Add a clean-string branch that streams normalized version parts directly from
  the original input strings.
- Keep whitespace-trimming behavior unchanged for non-clean inputs.
- Extend the focused regression command for the registered
  `startup-signals-version-compare-single-pass` probe with a sentinel test that
  forbids stripping clean differing values.

## Verification

- Focused startup version tests cover clean differing values, whitespace-trimmed
  differing values, `v`-prefix equivalence, suffix handling, and no materialized
  part lists.
- Changed-scope coverage uses the registered probe coverage command for
  `startup_signals.py`, the tests, PR-scoped registry tests, and the probe
  script.
- The registered probe compares `elapsed_ms_mean` for version comparisons before
  and after the slice.
