# Real Model HF Cache Fallback Memoization

## Slice

Optimize the Python real-model support helper that resolves a Hugging Face cache
snapshot when `refs/main` is unavailable.

## Probe

Registered PR-scoped probe: `real-model-support-hf-cache-latest-snapshot` in
`infra/perf/pr_scoped_probes.json`.

The probe covers:

- fallback snapshot discovery under a synthetic Hugging Face cache with 6,000
  snapshot directories;
- the existing common weight-file short-circuit path;
- focused tests and changed-scope coverage for `scripts/real_model_support.py`,
  `tests/test_real_model_support.py`, and `scripts/real_model_support_hf_cache_probe.py`.

## Change

Keep the `refs/main` fast path uncached so explicit cache refs can reflect file
updates immediately. Memoize only the fallback lexicographic snapshot scan by
`(model_id, cache_root)` for the process lifetime, returning immutable path and
warning strings from the cached helper.

This preserves the existing fallback semantics while avoiding repeated full
`snapshots/` scans during repeated real-model preflight/source resolution in the
same process.

## Validation Plan

Run the registered focused test command, changed-scope coverage command, and
registered probe locally on Linux. CI remains the required repository-level
PR-scoped performance validation source after push.
