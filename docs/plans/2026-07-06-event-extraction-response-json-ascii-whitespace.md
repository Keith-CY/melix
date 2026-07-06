# Event extraction response JSON ASCII whitespace fast path

## Scope

This Python-only performance slice targets `services/mlx-worker-python/worker/productization/event_extraction.py`, specifically the whitespace scans used by `_parse_response_json` when parsing direct JSON responses or fenced JSON responses from event-extraction model output.

The affected path is covered by the registered PR-scoped probe `event-extraction-response-json-fence-trim` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for the parser tests, changed-scope coverage, and synthetic response JSON parsing probe.

## Change

Use a shared whitespace skipper that handles common ASCII JSON whitespace with a cheap membership check before falling back to `str.isspace()` for compatibility with the existing broader whitespace behavior. This keeps parsing semantics unchanged while reducing per-character overhead in leading and trailing response scans.

A follow-up 2026-07-06 boundary-check slice keeps the same parser behavior but first checks whether the current character is at or below ASCII space. Common JSON boundary characters such as `}` and backticks can now break out before the ASCII-whitespace membership test, while non-ASCII whitespace still falls back to `str.isspace()`.

## Verification Plan

Run the registered focused parser tests, changed-scope coverage, and the registered PR-scoped probe locally on Linux. Compare the probe against an `origin/main` baseline worktree before accepting the slice.

No Swift runtime behavior is changed or locally claimed by this slice.
